"""Hermetic tests for SMTV chunked-download truncation handling.

A CDN that drops the connection mid-transfer returns a clean empty
``read()`` with no exception. Without a Content-Length check the partial
file was renamed to the final name and auto-transcribed — a silent
corruption. ``_stream_smtv_file`` now raises when fewer than
Content-Length bytes arrive. These tests fake ``urlopen`` so no network
is touched.
"""
from __future__ import annotations

import queue
import types
import urllib.request

import pytest

from app.services.download_service import DownloadService


class _FakeResp:
    def __init__(self, body_chunks, content_length):
        self._chunks = list(body_chunks)
        self.headers = (
            {"Content-Length": str(content_length)}
            if content_length is not None else {}
        )

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self, _n):
        return self._chunks.pop(0) if self._chunks else b""


def _svc():
    app = types.SimpleNamespace(download_events=queue.Queue())
    return DownloadService(app)  # type: ignore[arg-type]


def _patch_urlopen(monkeypatch, resp):
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=None: resp
    )


def test_stream_smtv_raises_on_truncated_download(tmp_path, monkeypatch):
    # Server promises 1000 bytes but the connection closes after 500.
    _patch_urlopen(monkeypatch, _FakeResp([b"x" * 500], content_length=1000))
    task = types.SimpleNamespace(cancelled=False)
    dest = str(tmp_path / "clip.mp4.part")
    with pytest.raises(RuntimeError, match="truncated"):
        _svc()._stream_smtv_file(task, "http://cdn/clip.mp4", dest)


def test_stream_smtv_accepts_complete_download(tmp_path, monkeypatch):
    _patch_urlopen(
        monkeypatch, _FakeResp([b"x" * 600, b"x" * 400], content_length=1000)
    )
    task = types.SimpleNamespace(cancelled=False)
    dest = str(tmp_path / "clip.mp4.part")
    _svc()._stream_smtv_file(task, "http://cdn/clip.mp4", dest)  # no raise
    with open(dest, "rb") as f:
        assert f.read() == b"x" * 1000


def test_stream_smtv_unknown_length_is_accepted(tmp_path, monkeypatch):
    # No Content-Length: truncation is undetectable, so don't false-alarm.
    _patch_urlopen(monkeypatch, _FakeResp([b"x" * 300], content_length=None))
    task = types.SimpleNamespace(cancelled=False)
    dest = str(tmp_path / "clip.mp4.part")
    _svc()._stream_smtv_file(task, "http://cdn/clip.mp4", dest)  # no raise


def test_stream_smtv_cancel_is_not_reported_as_truncation(tmp_path, monkeypatch):
    # Cancelled before completion must return cleanly, NOT raise truncated.
    _patch_urlopen(monkeypatch, _FakeResp([b"x" * 500], content_length=1000))
    task = types.SimpleNamespace(cancelled=True)
    dest = str(tmp_path / "clip.mp4.part")
    _svc()._stream_smtv_file(task, "http://cdn/clip.mp4", dest)  # no raise
