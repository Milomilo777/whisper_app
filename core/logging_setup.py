"""Centralized logging configuration.

The Tk app and the worker subprocess both call ``setup_logging`` once at
startup. The worker uses ``stream=sys.stderr`` so its JSON-on-stdout protocol
is never polluted.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .config import user_log_dir

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"
LOG_FILENAME = "app.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3

UI_LOGGER_NAME = "whisper.ui"

_configured = False


def _quiet_third_parties():
    for name in ("urllib3", "requests", "huggingface_hub", "filelock"):
        logging.getLogger(name).setLevel(logging.WARNING)


def setup_logging(level: str = "INFO", stream=None, filename: str | None = None):
    """Configure the root logger. Idempotent; safe to call more than once.

    ``filename`` overrides the default ``app.log`` so a second process can
    own its OWN log file. A ``RotatingFileHandler`` rolls over by renaming
    the active file (app.log -> app.log.1); on Windows you cannot rename a
    file another process still holds open, so when the GUI process and any
    worker subprocess share one app.log the rollover raises
    ``PermissionError`` (WinError 32), logging swallows it, the rotation
    silently fails and the file grows past the 5 MB x 3 cap. The worker
    therefore passes a per-process name (``worker-<pid>.log``) so each
    process rotates its own file independently.
    """
    global _configured

    log_dir = user_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / (filename or LOG_FILENAME)

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


def worker_log_filename(pid: int | None = None) -> str:
    """Per-process worker log name so each worker rotates its own file
    instead of fighting the GUI process over a single shared app.log
    (see ``setup_logging`` for the Windows-rename rationale)."""
    import os

    return f"worker-{pid if pid is not None else os.getpid()}.log"


def get_ui_logger() -> logging.Logger:
    """The user-facing log channel. Used by the Tk console widget feed."""
    return logging.getLogger(UI_LOGGER_NAME)


def open_log_folder():
    """Open the platformdirs log directory in the OS file manager."""
    import os
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
