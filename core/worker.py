"""Long-lived transcription worker.

Reads JSON commands from stdin, emits JSON events on stdout. The
protocol is intentionally frozen — adding fields is safe, renaming
or removing them breaks the parent UI.

Events emitted:
  - ``ready``                          : model loaded; accepting commands
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
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from typing import Any

from .config import load_config
from .logging_setup import setup_logging
from .task import TranscriptionTask
from .transcriber import get_model_error, load_existing_model, transcribe

logger = logging.getLogger(__name__)


# Audit A4: a per-worker session token assigned by the parent at
# spawn time via the WHISPER_WORKER_TOKEN env var. Attached to
# every emitted event so the parent can route correctly even if
# the OS recycles a PID between worker spawns. Empty when the
# env var is missing (older parents) — the parent falls back to
# matching by PID, preserving backwards compatibility.
_SESSION_TOKEN: str = os.environ.get("WHISPER_WORKER_TOKEN", "") or ""


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
    logger.info("Worker starting (pid=%d)", os.getpid())

    def log_cb(message: str) -> None:
        emit("log", message=message)

    def progress_cb(percent: float) -> None:
        emit("progress", percent=percent)

    if not load_existing_model(log_cb):
        detail = get_model_error() or "Existing model failed to load in worker"
        emit("startup_error", message=detail)
        return 1

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

    for line in sys.stdin:
        if len(line) > MAX_COMMAND_BYTES:
            emit(
                "error",
                message=(
                    f"command exceeds max length ({len(line)} > "
                    f"{MAX_COMMAND_BYTES} bytes); dropped"
                ),
            )
            continue
        line = line.strip()
        if not line:
            continue

        try:
            command = json.loads(line)
        except json.JSONDecodeError as e:
            emit("error", message=f"Invalid worker command: {e}")
            continue

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
            emit("started", file_path=file_path)

            def language_cb(lang: str, prob: float) -> None:
                emit("language_detected", language=lang, probability=prob, file_path=file_path)

            transcribe(task, progress_cb, log_cb, language_cb=language_cb)
            emit("done", file_path=file_path)
        except Exception as e:  # noqa: BLE001
            emit("error", message=str(e), file_path=file_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
