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

The parent matches events to workers via a per-process token sent in
the ``WHISPER_WORKER_TOKEN`` env var; we echo it back in every event.
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


def emit(event: str, **payload: Any) -> None:
    """Write a single JSON event line to stdout.

    Falls back to ``repr()``-coerced payloads when json.dumps raises;
    a silent drop would leave the parent stuck waiting for an event
    that will never arrive.
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
    print(line, flush=True)


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


def main() -> int:
    setup_logging(load_config().get("log_level", "INFO"))
    logger.info("Worker starting (pid=%d)", os.getpid())

    def log_cb(message: str) -> None:
        emit("log", message=message)

    def progress_cb(percent: float) -> None:
        emit("progress", percent=percent)

    if not load_existing_model(log_cb):
        detail = get_model_error() or "Model failed to load in worker"
        emit("startup_error", message=detail)
        return 1

    emit("ready")
    _start_heartbeat()

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
                # Stash on the task; transcriber reads getattr(task,
                # "language", None) when building kwargs.
                setattr(task, "language", forced_lang)
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
