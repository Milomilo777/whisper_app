"""Regression for frontend edge cases found by the edge-case hunt:

1. Re-run / Resume of a CLIPPED transcription must carry clip_start/clip_end to
   the new task — otherwise it silently transcribes the WHOLE file (the analogue
   of the already-fixed Download re-run bug). Covers _rerun_task, resume_task,
   _bulk_rerun, _bulk_resume.
2. App.cancel() must not flip an already-terminal task (finished/cancelled/error)
   back to "cancelled" (a stale right-click menu) — mirrors pause()/resume().

These call the App methods as unbound functions on a bare object (no Tk root) so
they stay hermetic.
"""
from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def App():
    if "faster_whisper" not in sys.modules:
        fw = types.ModuleType("faster_whisper")
        fw.WhisperModel = object  # type: ignore[attr-defined]
        sys.modules["faster_whisper"] = fw
    from app.app import App as _App
    return _App


class _Svc:
    def ensure_worker_ready(self, app):  # noqa: ARG002
        return True

    def send_control(self, t, c):  # noqa: ARG002
        pass


def _bare_app(App):
    a = App.__new__(App)
    a.queue = []
    a.transcription_service = _Svc()
    a.refresh = lambda *x, **k: None
    a.log = lambda *x, **k: None
    return a


def _clipped(file="movie.wav"):
    from core.task import TranscriptionTask
    t = TranscriptionTask(file)
    t.clip_start = 100.0
    t.clip_end = 160.0
    t.language = "fa"
    t.status = "finished"
    return t


def test_rerun_task_preserves_clip(App):
    a = _bare_app(App)
    App._rerun_task(a, _clipped())
    nt = a.queue[-1]
    assert nt.clip_start == 100.0 and nt.clip_end == 160.0
    assert nt.language == "fa"


def test_resume_task_preserves_clip(App):
    a = _bare_app(App)
    App.resume_task(a, _clipped())
    nt = a.queue[-1]
    assert nt.clip_start == 100.0 and nt.clip_end == 160.0
    assert nt.resume is True and nt.cancelled is False


def test_bulk_rerun_preserves_clip(App):
    a = _bare_app(App)
    App._bulk_rerun(a, [_clipped("a.wav"), _clipped("b.wav")])
    assert all(t.clip_start == 100.0 and t.clip_end == 160.0 for t in a.queue)
    assert len(a.queue) == 2


def test_bulk_resume_preserves_clip(App):
    a = _bare_app(App)
    App._bulk_resume(a, [_clipped("a.wav")])
    nt = a.queue[-1]
    assert nt.clip_start == 100.0 and nt.clip_end == 160.0 and nt.resume is True


def test_unclipped_rerun_stays_whole_file(App):
    from core.task import TranscriptionTask
    a = _bare_app(App)
    src = TranscriptionTask("plain.wav")  # no clip
    App._rerun_task(a, src)
    nt = a.queue[-1]
    assert nt.clip_start is None and nt.clip_end is None


def test_cancel_ignores_terminal_task(App):
    a = _bare_app(App)
    for term in ("finished", "cancelled", "error"):
        t = _clipped()
        t.status = term
        App.cancel(a, t)
        assert t.status == term  # not flipped to "cancelled"


def test_cancel_still_cancels_a_running_task(App):
    a = _bare_app(App)
    t = _clipped()
    t.status = "running"
    App.cancel(a, t)
    assert t.status == "cancelled" and t.cancelled is True
