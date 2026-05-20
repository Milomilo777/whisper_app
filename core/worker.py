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
from typing import Any

from .config import load_config
from .logging_setup import setup_logging
from .task import TranscriptionTask
from .transcriber import get_model_error, load_existing_model, transcribe

logger = logging.getLogger(__name__)


def emit(event: str, **payload: Any) -> None:
    """Write a single JSON event line to stdout.

    json.dumps may raise on non-serialisable values (e.g. a passed-
    through exception object). Fall back to a stringified payload so
    the parent always sees *something* and the worker never silently
    swallows an event.
    """
    payload["event"] = event
    try:
        line = json.dumps(payload)
    except (TypeError, ValueError):
        safe = {k: repr(v) for k, v in payload.items()}
        safe["event"] = event
        safe["_emit_warning"] = "payload was not JSON-serialisable; coerced via repr()"
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

    for line in sys.stdin:
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
