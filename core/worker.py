from __future__ import annotations

import json
import logging
import sys
from typing import Any

from .config import load_config
from .logging_setup import setup_logging
from .task import TranscriptionTask
from .transcriber import load_existing_model, transcribe

logger = logging.getLogger(__name__)

def emit(event: str, **payload: Any) -> None:
    payload["event"]=event
    print(json.dumps(payload), flush=True)

def main() -> int:
    setup_logging(load_config().get("log_level","INFO"))
    logger.info("Worker starting (pid=%d)", __import__("os").getpid())

    def log_cb(message):
        emit("log", message=message)

    def progress_cb(percent):
        emit("progress", percent=percent)

    if not load_existing_model(log_cb):
        emit("startup_error", message="Existing model failed to load in worker")
        return 1

    emit("ready")

    for line in sys.stdin:
        line=line.strip()
        if not line:
            continue

        try:
            command=json.loads(line)
        except json.JSONDecodeError as e:
            emit("error", message=f"Invalid worker command: {e}")
            continue

        action=command.get("action")
        if action == "shutdown":
            return 0

        if action != "transcribe":
            emit("error", message=f"Unknown worker command: {action}")
            continue

        file_path=command.get("file_path")
        if not file_path:
            emit("error", message="Missing input file")
            continue

        try:
            task=TranscriptionTask(file_path)
            forced_lang=command.get("language")
            if forced_lang:
                task.language=forced_lang
            emit("started", file_path=file_path)

            def language_cb(lang: str, prob: float) -> None:
                emit("language_detected", language=lang, probability=prob, file_path=file_path)

            transcribe(task, progress_cb, log_cb, language_cb=language_cb)
            emit("done", file_path=file_path)
        except Exception as e:
            emit("error", message=str(e), file_path=file_path)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
