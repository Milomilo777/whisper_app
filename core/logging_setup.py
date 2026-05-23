"""Centralized logging configuration.

Both the Tk app and the worker subprocess call :func:`setup_logging`
once at startup. The worker passes ``stream=sys.stderr`` so its JSON
stdout protocol stays uncontaminated.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import IO, Any

from .config import user_log_dir

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"
LOG_FILENAME = "app.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3

_configured = False


def _quiet_third_parties() -> None:
    for name in ("urllib3", "requests", "huggingface_hub", "filelock"):
        logging.getLogger(name).setLevel(logging.WARNING)


def setup_logging(
    level: str = "INFO",
    stream: "IO[Any] | None" = None,
) -> Path:
    """Configure the root logger. Idempotent; safe to call repeatedly.

    Returns the log-file path so the caller can print it in
    diagnostics. Subsequent calls only update the root level — they
    do not re-add handlers (which would double every message).
    """
    global _configured

    log_dir = user_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILENAME

    root = logging.getLogger()
    numeric = getattr(logging, str(level).upper(), logging.INFO)
    root.setLevel(numeric)

    if _configured:
        return log_file

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(stream or sys.stderr)
    stream_handler.setLevel(logging.WARNING)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    _quiet_third_parties()

    _configured = True
    return log_file


def open_log_folder() -> Path:
    """Open the platformdirs log directory in the OS file manager."""
    import subprocess

    folder = user_log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(folder))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(folder)], check=False)
    else:
        subprocess.run(["xdg-open", str(folder)], check=False)
    return folder


def read_recent_log(lines: int = 200) -> str:
    """Return the tail of ``app.log`` — used by the Show Log dialog.

    Returns an empty string when the log file doesn't exist yet
    (typical on the very first launch before any handler has fired).
    """
    log_file = user_log_dir() / LOG_FILENAME
    if not log_file.exists():
        return ""
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            buf = f.readlines()
    except OSError as e:
        return f"(could not read {log_file}: {e})"
    return "".join(buf[-max(1, lines):])
