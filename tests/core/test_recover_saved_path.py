"""Tests for DownloadService._recover_saved_path (self-healing saved path).

When the path parsed from yt-dlp stdout doesn't exist on disk (a rename, or
a filename character that slips past the utf-8 fix), _finish recovers the
real downloaded file so the size readout + auto-transcribe still work.
"""
from __future__ import annotations

import os
import time
import types

from app.services.download_service import DownloadService


def _svc() -> DownloadService:
    # _recover_saved_path doesn't touch the app object.
    return DownloadService(types.SimpleNamespace())  # type: ignore[arg-type]


def _task(folder: str, started: float) -> object:
    return types.SimpleNamespace(folder=folder, start_time=started)


def test_recovers_newest_media_file(tmp_path):
    started = time.time()
    real = tmp_path / "The Idaho Painter.mp4"
    real.write_bytes(b"video")
    (tmp_path / "The Idaho Painter.vtt").write_bytes(b"subs")   # ignored (not media)
    (tmp_path / "The Idaho Painter.srt").write_bytes(b"subs")   # ignored
    old = tmp_path / "unrelated-old.mp4"
    old.write_bytes(b"old")
    os.utime(old, (started - 10_000, started - 10_000))         # before this download
    got = _svc()._recover_saved_path(_task(str(tmp_path), started - 1), None)
    assert got == str(real)


def test_recovers_when_parsed_path_is_mojibake(tmp_path):
    # The real file carries a U+2019 apostrophe; the broken parser saw a
    # U+FFFD replacement char, so its path doesn't exist. Self-heal finds it.
    real = tmp_path / "Don’t Know About.mp4"
    real.write_bytes(b"v")
    parsed = str(tmp_path / "Don�t Know About.mp4")
    got = _svc()._recover_saved_path(_task(str(tmp_path), 0.0), parsed)
    assert got == str(real)


def test_returns_none_when_no_media(tmp_path):
    (tmp_path / "notes.txt").write_bytes(b"x")
    (tmp_path / "subs.srt").write_bytes(b"x")
    assert _svc()._recover_saved_path(_task(str(tmp_path), 0.0), None) is None


def test_returns_none_when_folder_missing():
    task = _task(os.path.join(os.sep, "nope", "zzz-does-not-exist"), 0.0)
    assert _svc()._recover_saved_path(task, None) is None
