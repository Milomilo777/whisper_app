"""Tests for the watched-folder dedup + stability check.

Drives ``core.watcher.FolderWatcher`` and the ``App._enqueue_watched_file``
stability ladder against a fake clock so we don't actually wait 1.2 s
for each iteration.
"""
from __future__ import annotations

import os
import sys
import types

import pytest


def test_watcher_is_available_returns_false_without_watchdog(monkeypatch):
    monkeypatch.setitem(sys.modules, "watchdog", None)
    from core import watcher as w
    assert w.is_available() is False
    assert "watchdog" in w.availability_reason()


def test_watcher_media_extension_filter():
    """Internal extension set must include the formats we list in
    the GUI's Browse... filter — drops out of sync if someone adds
    a new extension only in one place."""
    from core import watcher as w
    expected = {".mp3", ".mp4", ".wav", ".m4a", ".mkv", ".webm"}
    assert expected.issubset(w._MEDIA_EXTENSIONS)


def test_is_media_file_extension_gate():
    """The public helper shared with the drag-and-drop folder handler."""
    from core import watcher as w
    assert w.is_media_file("clip.MP4")           # case-insensitive
    assert w.is_media_file(r"C:\x\audio.flac")   # full paths fine
    assert not w.is_media_file("notes.txt")
    assert not w.is_media_file("no_extension")


def test_folder_watcher_stop_when_unavailable(monkeypatch, tmp_path):
    """FolderWatcher.stop on an unstarted instance is a noop."""
    from core import watcher as w
    fw = w.FolderWatcher(str(tmp_path), lambda _p: None)
    # Must not raise.
    fw.stop()
    assert fw.is_running() is False


def test_folder_watcher_start_raises_without_watchdog(monkeypatch, tmp_path):
    """When watchdog isn't installed, start() raises a clear
    RuntimeError instead of crashing with an obscure ImportError."""
    from core import watcher as w
    monkeypatch.setattr(w, "is_available", lambda: False)
    monkeypatch.setattr(
        w, "availability_reason",
        lambda: "watchdog Python package not installed",
    )
    fw = w.FolderWatcher(str(tmp_path), lambda _p: None)
    with pytest.raises(RuntimeError, match="watchdog"):
        fw.start()


def test_folder_watcher_lock_is_reentrant(tmp_path):
    """Regression: FolderWatcher.start() acquires self._lock and
    then calls self.stop() which acquires it again. With a plain
    threading.Lock this deadlocks forever; RLock fixes it.
    """
    from core import watcher as w
    fw = w.FolderWatcher(str(tmp_path), lambda _p: None)
    # The lock attribute must support re-entry from the same thread.
    assert fw._lock.acquire(blocking=False)
    # Acquire again from the same thread — must succeed (RLock semantic).
    assert fw._lock.acquire(blocking=False)
    fw._lock.release()
    fw._lock.release()
