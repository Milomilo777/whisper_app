"""Long-lived transcription worker.

Reads JSON commands from stdin, emits JSON events on stdout. The
protocol is intentionally frozen — adding fields is safe, renaming
or removing them breaks the parent UI.

Events emitted:
  - ``ready``  ([device, compute_type, requested_device, downgraded])
                                       : model loaded; accepting commands.
    The device fields are additive (R3) — they report which device the model
    actually loaded onto and whether a requested CUDA load self-healed onto
    CPU. Older parents that don't read them keep working unchanged.
  - ``startup_error``                  : model failed to load; exiting
  - ``log``       (message)             : free-text log line
  - ``progress``  (percent)             : current task progress 0–100
  - ``language_detected`` (language, probability, file_path)
  - ``started``   (file_path)           : task accepted
  - ``done``      (file_path)           : task finished writing outputs
  - ``error``     (message[, file_path]): task or worker error

Commands accepted on stdin (one JSON object per line):
  - ``{"action": "shutdown"}``
  - ``{"action": "transcribe", "file_path": "...", "language": "..."}``
  - ``{"action": "cancel"}``   : cancel the in-flight task (flush checkpoint)
  - ``{"action": "pause"}``    : pause the in-flight task at the next segment
  - ``{"action": "resume"}``   : resume a paused task

cancel/pause/resume are *control* commands: a dedicated reader thread
applies them to the running task immediately, because the main thread is
blocked inside ``transcribe()`` and cannot read stdin itself. The
transcriber polls ``task.cancelled`` / ``task.paused`` between segments.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
from typing import Any

from .config import load_config
from .logging_setup import setup_logging
from .task import TranscriptionTask
from .transcriber import (
    get_effective_device,
    get_model_error,
    load_existing_model,
    resume_transcription,
    transcribe,
)

logger = logging.getLogger(__name__)


# Audit A4: a per-worker session token assigned by the parent at
# spawn time via the WHISPER_WORKER_TOKEN env var. Attached to
# every emitted event so the parent can route correctly even if
# the OS recycles a PID between worker spawns. Empty when the
# env var is missing (older parents) — the parent falls back to
# matching by PID, preserving backwards compatibility.
_SESSION_TOKEN: str = os.environ.get("WHISPER_WORKER_TOKEN", "") or ""


# The task currently being transcribed, shared between the main thread
# (which runs transcribe()) and the stdin-reader thread (which applies
# cancel/pause/resume). Guarded by a lock; bool-flag writes on the task
# itself are atomic under the GIL, which is all the transcriber's
# between-segment poll needs.
_state_lock = threading.Lock()
_current_task: "TranscriptionTask | None" = None


def _set_current_task(task: "TranscriptionTask | None") -> None:
    global _current_task
    with _state_lock:
        _current_task = task


def _apply_control(action: str) -> None:
    """Apply a control command to the in-flight task, if any.

    No-op when no task is running (a stray cancel/pause between tasks is
    harmless — each transcribe builds a fresh task with the flags clear).
    """
    with _state_lock:
        task = _current_task
    if task is None:
        return
    if action == "cancel":
        task.cancelled = True
    elif action == "pause":
        task.paused = True
    elif action == "resume":
        task.paused = False


def emit(event: str, **payload: Any) -> None:
    """Write a single JSON event line to stdout.

    json.dumps may raise on non-serialisable values (e.g. a passed-
    through exception object). Fall back to a stringified payload so
    the parent always sees *something* and the worker never silently
    swallows an event.
    """
    payload["event"] = event
    if _SESSION_TOKEN:
        payload["_token"] = _SESSION_TOKEN
    try:
        line = json.dumps(payload)
    except (TypeError, ValueError) as e:
        # Audit B4: log the actual encoding error before falling
        # back. Without this the parent sees ``_emit_warning`` but
        # the real TypeError ("Object of type Exception is not JSON
        # serializable", etc.) is lost — a bug magnet for future
        # maintainers.
        logger.exception(
            "Worker event payload not JSON-serialisable; coercing via repr. "
            "event=%s payload_types=%r",
            event,
            {k: type(v).__name__ for k, v in payload.items()},
        )
        safe = {k: repr(v) for k, v in payload.items()}
        safe["event"] = event
        safe["_emit_warning"] = (
            f"payload was not JSON-serialisable ({type(e).__name__}: {e}); "
            "coerced via repr()"
        )
        line = json.dumps(safe)
    print(line, flush=True)


def main() -> int:
    setup_logging(load_config().get("log_level", "INFO"))
    # Make on-demand-installed optional packages (stable-ts → torch)
    # importable; alignment runs in THIS worker process.
    try:
        from .optional_deps import activate as _activate_extras
        _activate_extras()
    except Exception:  # noqa: BLE001
        pass
    logger.info("Worker starting (pid=%d)", os.getpid())

    def log_cb(message: str) -> None:
        emit("log", message=message)

    def progress_cb(percent: float) -> None:
        emit("progress", percent=percent)

    if not load_existing_model(log_cb):
        detail = get_model_error() or "Existing model failed to load in worker"
        emit("startup_error", message=detail)
        return 1

    # R3: tell the parent which device the model actually loaded onto so the
    # UI can show a GPU/CPU badge and warn on a silent CUDA->CPU downgrade.
    # Strictly ADDITIVE to the frozen protocol — old parents ignore the extra
    # fields; new parents read them with .get() defaults. Guarded so a probe
    # failure never blocks the (essential) bare ``ready`` signal.
    try:
        eff = get_effective_device()
        emit(
            "ready",
            device=eff.device,
            compute_type=eff.compute_type,
            requested_device=eff.requested_device,
            downgraded=eff.downgraded,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not read effective device; emitting bare ready")
        emit("ready")

    # Audit D8: heartbeat thread. Without this the parent has no way
    # to distinguish "worker is mid-CPU-bound-transcribe" from
    # "worker silently wedged". We emit a tiny heartbeat every 5 s
    # so the parent can declare the worker dead if heartbeats stop.
    # Daemon thread — dies with the process; no shutdown signal
    # needed.
    HEARTBEAT_INTERVAL_SECONDS = 5.0

    def _heartbeat() -> None:
        while True:
            time.sleep(HEARTBEAT_INTERVAL_SECONDS)
            try:
                emit("heartbeat", ts=time.time())
            except Exception:
                logger.exception("heartbeat emit failed")

    threading.Thread(target=_heartbeat, name="worker-heartbeat",
                     daemon=True).start()

    # Reasonable max line size — a single JSON command should be
    # under a few KB. Anything past 1 MB is either a runaway parent
    # or an attempt to OOM the worker; reject loudly instead of
    # buffering up megabytes of garbage.
    MAX_COMMAND_BYTES = 1 << 20  # 1 MB

    # Transcribe/shutdown commands are handed to the main thread via this
    # queue; cancel/pause/resume are applied inline by the reader thread.
    cmd_queue: "queue.Queue[dict[str, Any] | None]" = queue.Queue()

    def _stdin_reader() -> None:
        """Read stdin concurrently with transcription.

        The main thread blocks inside transcribe(), so it cannot read
        its own control commands. This thread does: it applies
        cancel/pause/resume to the in-flight task immediately and queues
        everything else (transcribe/shutdown) for the main loop. A None
        sentinel on stdin-close tells the main loop to exit.
        """
        try:
            for raw in sys.stdin:
                if len(raw) > MAX_COMMAND_BYTES:
                    emit(
                        "error",
                        message=(
                            f"command exceeds max length ({len(raw)} > "
                            f"{MAX_COMMAND_BYTES} bytes); dropped"
                        ),
                    )
                    continue
                line = raw.strip()
                if not line:
                    continue
                try:
                    command = json.loads(line)
                except json.JSONDecodeError as e:
                    emit("error", message=f"Invalid worker command: {e}")
                    continue
                if command.get("action") in ("cancel", "pause", "resume"):
                    _apply_control(command["action"])
                else:
                    cmd_queue.put(command)
        finally:
            cmd_queue.put(None)

    threading.Thread(target=_stdin_reader, name="worker-stdin",
                     daemon=True).start()

    while True:
        command = cmd_queue.get()
        if command is None:  # stdin closed — parent gone
            return 0

        action = command.get("action")
        if action == "shutdown":
            return 0

        if action != "transcribe":
            emit("error", message=f"Unknown worker command: {action}")
            continue

        file_path = command.get("file_path")
        if not file_path:
            emit("error", message="Missing input file")
            continue

        try:
            task = TranscriptionTask(file_path)
            forced_lang = command.get("language")
            if forced_lang:
                task.language = forced_lang
            # Resume-from-cancellation: when the parent flagged the
            # task as a resume, attempt the partial-checkpoint path
            # first. If it returns False (stale checkpoint, changed
            # model/config, ffmpeg slice failed, etc.) we fall back to
            # a full re-transcribe so the user always gets an output
            # rather than an error.
            task.resume = bool(command.get("resume", False))
            # Time-slice (Transcribe-tab time range): transcribe only this
            # span via clip_timestamps. None = whole file.
            task.clip_start = command.get("clip_start")
            task.clip_end = command.get("clip_end")
            # Per-task output formats (worker's config snapshot is stale).
            task.output_formats = command.get("output_formats")
            # A clipped run must NOT resume: the checkpoint is keyed to the
            # whole file with no clip marker, so resuming would transcribe
            # past clip_end. Clips are short — re-transcribe the slice fresh.
            if task.clip_start or task.clip_end:
                task.resume = False
            # Publish the task so the reader thread can cancel/pause it.
            _set_current_task(task)
            emit("started", file_path=file_path)

            def language_cb(lang: str, prob: float) -> None:
                emit("language_detected", language=lang, probability=prob, file_path=file_path)

            try:
                did_resume = False
                if task.resume:
                    did_resume = resume_transcription(
                        task, progress_cb, log_cb, language_cb=language_cb
                    )
                if not did_resume:
                    transcribe(task, progress_cb, log_cb, language_cb=language_cb)
                emit(
                    "done",
                    file_path=file_path,
                    outputs=getattr(task, "output_paths", None) or [],
                )
            finally:
                _set_current_task(None)
        except Exception as e:  # noqa: BLE001
            emit("error", message=str(e), file_path=file_path)


if __name__ == "__main__":
    raise SystemExit(main())
