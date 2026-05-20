"""Watched folder integration.

When the user configures a folder under ``app_config["watched_folder"]``
and toggles ``watched_folder_enabled`` on, any media file dropped
into that folder is enqueued for transcription automatically.

Wraps ``watchdog`` lazily so the import doesn't fail when the
wheel isn't installed (the UI checkbox stays disabled with a
clear "unavailable" label in that case).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


_MEDIA_EXTENSIONS = {
    ".mp3", ".mp4", ".wav", ".m4a", ".mkv", ".webm", ".flac",
    ".ogg", ".aac", ".aiff", ".opus", ".mov",
}


def is_available() -> bool:
    try:
        import watchdog  # type: ignore[import-untyped] # noqa: F401
    except ImportError:
        return False
    return True


def availability_reason() -> str:
    if is_available():
        return ""
    return "watchdog Python package not installed"


class FolderWatcher:
    """One-folder daemon watcher.

    Pass an ``on_new_file(path)`` callback that the App's main
    thread will receive via the existing event queue. The callback
    is invoked from a watchdog worker thread, so callers must
    push to a Tk-safe queue rather than touch widgets directly.
    """

    def __init__(self, folder: str, on_new_file: Callable[[str], None]) -> None:
        self.folder = folder
        self.on_new_file = on_new_file
        self._observer: Any = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if not is_available():
            raise RuntimeError(availability_reason())
        from watchdog.events import FileSystemEventHandler  # type: ignore[import-untyped]
        from watchdog.observers import Observer  # type: ignore[import-untyped]

        cb = self.on_new_file
        media_exts = _MEDIA_EXTENSIONS

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):  # noqa: N805
                if event.is_directory:
                    return
                path = event.src_path
                if isinstance(path, bytes):
                    path = path.decode("utf-8", "replace")
                if os.path.splitext(path)[1].lower() not in media_exts:
                    return
                try:
                    cb(path)
                except Exception:  # noqa: BLE001
                    logger.exception("Watcher callback raised on %s", path)

        with self._lock:
            self.stop()
            observer = Observer()
            observer.schedule(_Handler(), self.folder, recursive=False)
            observer.daemon = True
            observer.start()
            self._observer = observer
            logger.info("FolderWatcher started for %s", self.folder)

    def stop(self) -> None:
        with self._lock:
            obs = self._observer
            self._observer = None
        if obs is None:
            return
        try:
            obs.stop()
            obs.join(timeout=2.0)
        except Exception:  # noqa: BLE001
            pass
        logger.info("FolderWatcher stopped")

    def is_running(self) -> bool:
        with self._lock:
            obs = self._observer
        return obs is not None and getattr(obs, "is_alive", lambda: False)()
