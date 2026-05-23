"""Transcription worker subprocess.

Protocol — every event is one JSON object per line on stdout:

  * ``ready``                      : model loaded; accepting commands
  * ``startup_error`` (message)    : model failed to load; exiting
  * ``log``       (message)        : free-text log line
  * ``progress``  (percent)        : current task progress 0-100
  * ``language_detected`` (language, probability, file_path)
  * ``started``   (file_path)      : task accepted
  * ``done``      (file_path)      : task finished writing outputs
  * ``error``     (message, file_path?) : task or worker-level error
  * ``heartbeat`` (ts)             : emitted every 5 s by a daemon thread

Commands (one JSON object per line on stdin):

  * ``{"action": "shutdown"}``
  * ``{"action": "transcribe", "file_path": "...", "language": "..."}``

Exit codes
----------

* ``0`` — graceful exit. The parent sent ``{"action":"shutdown"}`` or
  closed our stdin (the parent's shutdown path may close stdin
  instead of writing a shutdown command). Either way the worker is
  not in an error state.
* ``1`` — startup-time model load failed (``startup_error`` was emitted).

The worker can not by itself tell "parent crashed" apart from
"parent closed stdin on purpose" — both look like EOF on stdin. The
parent's ``worker_exit`` handler is responsible for resurrecting
stalled queues when the worker dies with no in-flight task (see
``app/app.py`` — ``_handle_event`` for ``worker_exit``).

The parent matches events to workers via a per-process token sent in
the ``WHISPER_WORKER_TOKEN`` env var; we echo it back in every event.
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
from .error_messages import friendly_error
from .logging_setup import setup_logging
from .task import TranscriptionTask
from .transcriber import (
    get_model_error,
    load_existing_model,
    transcribe,
)

logger = logging.getLogger(__name__)

# Per-spawn session token. The parent assigns this via the env var so
# event routing survives PID recycling.
_SESSION_TOKEN: str = os.environ.get("WHISPER_WORKER_TOKEN", "") or ""

# Reject runaway commands — a single JSON line should be at most a
# few KB. Anything past 1 MB is either a bug or an OOM attempt.
MAX_COMMAND_BYTES = 1 << 20

HEARTBEAT_INTERVAL_SECONDS = 5.0

# Lifecycle events must never be silently dropped — the parent uses
# these to drive UI state transitions.
LIFECYCLE_EVENTS: frozenset[str] = frozenset({
    "ready", "startup_error", "done", "error", "worker_exit",
})

# Serialises stdout writes so the heartbeat daemon thread and the
# main thread can't interleave bytes inside a single JSON line.
_emit_lock = threading.Lock()


def emit(event: str, **payload: Any) -> None:
    """Write a single JSON event line to stdout.

    Falls back to ``repr()``-coerced payloads when json.dumps raises;
    a silent drop would leave the parent stuck waiting for an event
    that will never arrive. The write is guarded by ``_emit_lock`` so
    the heartbeat daemon thread and the main thread can't interleave
    bytes — ``print(line, flush=True)`` is not atomic on CPython
    (write + flush yields the GIL between them).
    """
    payload["event"] = event
    if _SESSION_TOKEN:
        payload["_token"] = _SESSION_TOKEN
    try:
        line = json.dumps(payload)
    except (TypeError, ValueError) as e:
        logger.exception(
            "Worker payload not JSON-serialisable; coercing. "
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
    with _emit_lock:
        print(line, flush=True)


def _read_command_line() -> bytes | None:
    """Read one command line from stdin with a hard size cap.

    Returns the raw bytes (including trailing ``\\n`` if present), or
    ``None`` on EOF. If the line exceeds :data:`MAX_COMMAND_BYTES`
    bytes, it is consumed up to the next newline and discarded;
    callers receive an empty bytes object so they can emit an error
    and continue (the size guard would otherwise be defeated by
    Python buffering the whole line in RAM before the length check
    runs).
    """
    stream = sys.stdin.buffer
    # +1 lets us tell "exactly at the cap" from "past the cap".
    raw = stream.readline(MAX_COMMAND_BYTES + 1)
    if not raw:
        return None
    if len(raw) > MAX_COMMAND_BYTES and not raw.endswith(b"\n"):
        # Oversize line with no newline in the first window — drain
        # the rest in fixed-size chunks until we find one or hit EOF.
        # This bounds RSS at MAX_COMMAND_BYTES + 64 KiB regardless of
        # the attacker's line length.
        while True:
            extra = stream.readline(64 * 1024)
            if not extra or extra.endswith(b"\n"):
                break
        return b""  # caller treats empty as "oversize, dropped"
    return raw


# ---------------------------------------------------------- shutdown plumbing
#
# Stdin is read by a daemon thread (``_start_command_reader``) so a
# shutdown command can arrive even while the main thread is sitting
# inside ``transcribe()``. The reader sets ``_shutting_down`` and, if
# a task is in flight, sets ``_active_task.cancelled = True`` so the
# segment loop bails on the next iteration instead of waiting for the
# full file to finish (runtime-probe WARN #15).

_pending_commands: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=64)
_active_task: TranscriptionTask | None = None
_shutting_down: threading.Event = threading.Event()


def _start_command_reader() -> None:
    def _loop() -> None:
        while True:
            raw = _read_command_line()
            if raw is None:
                # Parent closed stdin — treat as shutdown.
                _shutting_down.set()
                _pending_commands.put(None)
                return
            if raw == b"":
                emit(
                    "error",
                    message=(
                        f"command exceeds max length (> {MAX_COMMAND_BYTES} "
                        "bytes); dropped"
                    ),
                )
                continue
            if len(raw) > MAX_COMMAND_BYTES:
                emit(
                    "error",
                    message=(
                        f"command exceeds max length ({len(raw)} > "
                        f"{MAX_COMMAND_BYTES} bytes); dropped"
                    ),
                )
                continue
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except (UnicodeDecodeError, AttributeError) as exc:
                emit("error", message=f"Invalid command bytes: {exc}")
                continue
            if not line:
                continue
            try:
                command = json.loads(line)
            except json.JSONDecodeError as exc:
                emit("error", message=f"Invalid worker command: {exc}")
                continue

            # Honour shutdown immediately, regardless of whether a task
            # is in flight — this is the whole point of moving the
            # reader off the main thread.
            if command.get("action") == "shutdown":
                _shutting_down.set()
                if _active_task is not None:
                    _active_task.cancelled = True
                _pending_commands.put(None)
                return

            try:
                _pending_commands.put(command, timeout=5.0)
            except queue.Full:
                emit("error", message="Worker command queue full; dropped")

    threading.Thread(
        target=_loop, name="worker-stdin-reader", daemon=True,
    ).start()


def _start_heartbeat() -> None:
    """Spawn a daemon thread that emits a tick every 5 s.

    The parent's watchdog uses these to distinguish "worker is
    mid-CPU-bound transcribe" from "worker silently wedged". Daemon
    thread: dies with the process; no shutdown signal needed.
    """
    def _hb() -> None:
        while True:
            time.sleep(HEARTBEAT_INTERVAL_SECONDS)
            try:
                emit("heartbeat", ts=time.time())
            except Exception:
                logger.exception("heartbeat emit failed")
    threading.Thread(target=_hb, name="worker-heartbeat", daemon=True).start()


def _reconfigure_stdio_utf8() -> None:
    """Force stdin/stdout to UTF-8 regardless of the host code page.

    On a Chinese-Windows install (``cp936``) or Vietnamese
    (``cp1258``) the JSON command containing a unicode path arrives
    mangled because the parent writes UTF-8 bytes but Python's
    ``sys.stdin`` text wrapper decodes under the locale default. We
    push the wrapper into UTF-8 with ``errors="replace"`` so a single
    bad byte doesn't crash the worker mid-command.
    """
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            logger.debug("stdio reconfigure to utf-8 failed", exc_info=True)


def main() -> int:
    _reconfigure_stdio_utf8()
    setup_logging(load_config().get("log_level", "INFO"))
    logger.info("Worker starting (pid=%d)", os.getpid())

    def log_cb(message: str) -> None:
        emit("log", message=message)

    def progress_cb(percent: float) -> None:
        emit("progress", percent=percent)

    # Start the heartbeat BEFORE load_existing_model. A cold-disk
    # 3-GB Whisper model can take 15-30 s to mmap on Windows; the
    # parent's "Loading Whisper model..." dialog wants regular
    # heartbeats during that wait so any future watchdog can tell
    # "slow load" from "wedged worker". Doing this after the load
    # means the parent sees zero heartbeats for the entire load
    # window — exactly when it most wants them (P0-2).
    _start_heartbeat()

    if not load_existing_model(log_cb):
        detail = get_model_error() or "Model failed to load in worker"
        emit("startup_error", message=detail)
        return 1

    emit("ready")
    _start_command_reader()

    global _active_task
    while True:
        try:
            command = _pending_commands.get(timeout=1.0)
        except queue.Empty:
            if _shutting_down.is_set():
                logger.info("Worker shutting down")
                return 0
            continue
        if command is None or _shutting_down.is_set():
            logger.info("Worker shutting down")
            return 0

        action = command.get("action")
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
                # Stash on the task; transcriber reads getattr(task,
                # "language", None) when building kwargs.
                setattr(task, "language", forced_lang)
            # Expose the active task to the stdin reader so a
            # shutdown command can flip task.cancelled and the
            # segment loop bails on the next iteration.
            _active_task = task
            emit("started", file_path=file_path)

            def language_cb(lang: str, prob: float) -> None:
                emit(
                    "language_detected",
                    language=lang, probability=prob, file_path=file_path,
                )

            transcribe(task, progress_cb, log_cb, language_cb=language_cb)
            emit("done", file_path=file_path)
        except Exception as e:  # noqa: BLE001
            # Translate the raw exception into the user-facing
            # actionable string before sending to the parent.
            friendly, suggestion = friendly_error(e, file_path=file_path)
            emit(
                "error",
                message=friendly,
                suggestion=suggestion,
                file_path=file_path,
            )
        finally:
            _active_task = None


if __name__ == "__main__":
    raise SystemExit(main())
