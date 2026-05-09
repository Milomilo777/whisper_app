import json
import sys

from .task import TranscriptionTask
from .transcriber import load_existing_model, transcribe

def emit(event, **payload):
    payload["event"]=event
    print(json.dumps(payload), flush=True)

def main():
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
            emit("started", file_path=file_path)
            transcribe(task, progress_cb, log_cb)
            emit("done", file_path=file_path)
        except Exception as e:
            emit("error", message=str(e), file_path=file_path)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
