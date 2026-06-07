"""Fixpack backlog regressions for app.services.download_service — downloadsvc.

Three medium/low defects from the backlog triage, all proven hermetically
(no Tk root, no network, no model, no subprocess):

1. enqueue_from_form reused a STALE ``_smtv_episode`` for a DIFFERENT SMTV url.
   The 800ms format-lookup is debounced, so pasting SMTV url A, replacing it
   with SMTV url B, and clicking Download before B's lookup fired reused
   episode A's CDN urls/transcript for B. Fixed by matching ``page_url == url``.

2. A typed time-range bound at/beyond the probed video length was accepted and
   shipped to yt-dlp; a start past the end builds a "*<dur>-" arg that
   downloads nothing. Fixed by dropping bounds >= duration when duration > 0.

3. DownloadService.poll() did ``int(payload)`` with no guard; a NaN / inf /
   non-numeric progress percent raised and — poll() having no try/except —
   skipped the after(300) re-arm, WEDGING the pump for every task. Fixed by a
   defensive finite-coercion.
"""
from __future__ import annotations

import sys
import types

import pytest

from app.services.download_service import DownloadService
from core.integrations import smtv as smtv_mod


SMTV_A = "https://www.suprememastertv.com/en1/v/111111.html"
SMTV_B = "https://www.suprememastertv.com/en1/v/222222.html"


# --------------------------------------------------------------------------
# Shared bare-app harness (App.__new__ + stubbed attrs, no Tk root)
# --------------------------------------------------------------------------


def _episode(page_url: str) -> smtv_mod.SmtvEpisode:
    return smtv_mod.SmtvEpisode(
        vid=page_url.rsplit("/", 1)[-1].split(".")[0],
        title="Episode",
        page_url=page_url,
        lang_prefix="en",
        files=[
            smtv_mod.SmtvFile(
                quality="396p",
                relative_path="clip.mp4",
                download_url=f"https://cdn.example/{page_url[-12:]}?file=clip.mp4",
            )
        ],
    )


class _Var:
    def __init__(self, value: str = "") -> None:
        self._v = value

    def get(self) -> str:
        return self._v

    def set(self, v) -> None:  # noqa: ANN001
        self._v = v


def _bare_app(monkeypatch, tmp_path, *, url: str, episode):
    """A stub App carrying exactly what enqueue_from_form touches."""
    # Stub the App import lazily so faster_whisper isn't needed.
    if "faster_whisper" not in sys.modules:
        fw = types.ModuleType("faster_whisper")
        fw.WhisperModel = object  # type: ignore[attr-defined]
        sys.modules["faster_whisper"] = fw
    from app.app import App

    # Don't let save_config touch the real config file.
    import app.services.download_service as ds
    monkeypatch.setattr(ds, "save_config", lambda *a, **k: None)
    # enqueue_from_form imports tkinter.messagebox lazily; a warning path
    # would otherwise try to spin up a Tk root. Neutralise it so a validation
    # warning is observable (recorded) without any Tk.
    import tkinter.messagebox as _mb
    warnings: list = []
    monkeypatch.setattr(_mb, "showwarning", lambda *a, **k: warnings.append(a))

    app = App.__new__(App)
    app.download_url_var = _Var(url)
    app.download_folder_var = _Var(str(tmp_path))
    app.download_mode_var = _Var("Audio and video")
    app.audio_format_var = _Var("")
    app.video_format_var = _Var("SD 396p")
    app.output_format_var = _Var("mp4")
    app.audio_format_map = {}
    app.video_format_map = {"SD 396p": {"kind": "smtv", "mode": "video-396",
                                        "quality": "396p", "url": "x"}}
    app._smtv_episode = episode
    app.app_config = {}
    app.current_video_title = "Episode"
    app.current_video_language = "en"
    app.download_subtitles_var = _Var("")
    app.subtitle_lang_var = _Var("")
    app.download_start_time_var = _Var("")
    app.download_end_time_var = _Var("")
    app._download_duration = 0.0
    app.smtv_download_all_parts_var = None
    app.download_queue = []
    app.refresh_download_queue = lambda *a, **k: None

    captured: dict = {}

    class _Events:
        def put(self, item) -> None:  # noqa: ANN001
            captured.setdefault("events", []).append(item)

    app.download_events = _Events()

    svc = DownloadService(app)
    svc.process_queue = lambda *a, **k: None  # don't spawn a worker thread
    return app, svc, captured


# --------------------------------------------------------------------------
# 1. Stale _smtv_episode must NOT be reused for a different SMTV url
# --------------------------------------------------------------------------


def test_stale_smtv_episode_not_reused_for_different_url(monkeypatch, tmp_path):
    """Episode A stashed, url is B -> the task must NOT be an SMTV task."""
    app, svc, _ = _bare_app(monkeypatch, tmp_path, url=SMTV_B, episode=_episode(SMTV_A))
    # With the episode rejected, this becomes a normal (non-SMTV) download, so
    # an audio format is required — supply one so we exercise the enqueue, not
    # the missing-format warning.
    app.audio_format_var = _Var("Best audio")
    app.audio_format_map = {"Best audio": {"kind": "best_audio"}}
    app.video_format_map = {"SD 396p": {"kind": "format_id", "format_id": "18"}}
    svc.enqueue_from_form()
    assert len(app.download_queue) == 1
    task = app.download_queue[0]
    # The mismatched episode was dropped: no SMTV episode pinned onto the task,
    # and subtitles/lang are NOT force-blanked as they are for an SMTV task.
    assert "episode" not in (task.format_info or {})


def test_matching_smtv_episode_is_reused(monkeypatch, tmp_path):
    """Episode B stashed, url is B -> reused as an SMTV task (episode pinned)."""
    ep = _episode(SMTV_B)
    app, svc, _ = _bare_app(monkeypatch, tmp_path, url=SMTV_B, episode=ep)
    svc.enqueue_from_form()
    assert len(app.download_queue) == 1
    task = app.download_queue[0]
    assert task.format_info.get("episode") is ep


# --------------------------------------------------------------------------
# 2. Time-range bounds at/beyond the probed duration are dropped
# --------------------------------------------------------------------------


def _enqueue_with_range(monkeypatch, tmp_path, *, duration, start, end):
    # A plain (non-SMTV) youtube-ish url so the duration guard is active.
    app, svc, _ = _bare_app(
        monkeypatch, tmp_path, url="https://youtu.be/abc", episode=None
    )
    # Plain url needs a real audio format selected (audio_required True).
    app.audio_format_var = _Var("Best audio")
    app.audio_format_map = {"Best audio": {"kind": "best_audio"}}
    app.video_format_map = {"SD 396p": {"kind": "format_id", "format_id": "18"}}
    app._download_duration = duration
    app.download_start_time_var = _Var(start)
    app.download_end_time_var = _Var(end)
    svc.enqueue_from_form()
    assert len(app.download_queue) == 1
    return app.download_queue[0]


def test_end_beyond_duration_is_dropped(monkeypatch, tmp_path):
    # 2-minute video, end typed at 5:00 -> dropped (equivalent to "to the end").
    task = _enqueue_with_range(
        monkeypatch, tmp_path, duration=120.0, start="0:30", end="5:00"
    )
    assert task.section_start == 30.0
    assert task.section_end is None


def test_start_beyond_duration_is_dropped(monkeypatch, tmp_path):
    # start past the end is an empty slice -> dropped (not a broken "*300-").
    task = _enqueue_with_range(
        monkeypatch, tmp_path, duration=120.0, start="5:00", end=""
    )
    assert task.section_start is None
    assert task.section_end is None


def test_in_range_bounds_survive(monkeypatch, tmp_path):
    task = _enqueue_with_range(
        monkeypatch, tmp_path, duration=600.0, start="0:51", end="1:25"
    )
    assert task.section_start == 51.0
    assert task.section_end == 85.0


def test_unknown_duration_leaves_bounds_untouched(monkeypatch, tmp_path):
    # duration 0 (live / unknown) -> the guard must not strip a valid range.
    task = _enqueue_with_range(
        monkeypatch, tmp_path, duration=0.0, start="5:00", end="9:00"
    )
    assert task.section_start == 300.0
    assert task.section_end == 540.0


# --------------------------------------------------------------------------
# 3. poll() must survive a NaN / inf / non-numeric progress percent
# --------------------------------------------------------------------------


class _PollApp:
    """Minimal app for driving DownloadService.poll once."""

    def __init__(self, events):
        from queue import Queue
        self.download_events = Queue()
        for e in events:
            self.download_events.put(e)
        self._closing = False
        self.rearmed = False
        self.download_current = None

    def after(self, _ms, _cb):  # noqa: ANN001
        # Record that poll re-armed itself (proof the pump survived).
        self.rearmed = True

    def refresh_download_queue(self):
        pass

    def log(self, *a, **k):  # noqa: ANN002, ANN003
        pass


class _Task:
    def __init__(self):
        self.progress = 0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "oops", None])
def test_poll_survives_bad_progress_value(bad):
    task = _Task()
    app = _PollApp([("progress", task, bad)])
    DownloadService(app).poll()
    # The pump re-armed (did not crash out of poll) ...
    assert app.rearmed is True
    # ... and the bad value never produced a garbage progress.
    assert 0 <= task.progress <= 100


def test_poll_normal_progress_still_works():
    task = _Task()
    app = _PollApp([("progress", task, 42.7)])
    DownloadService(app).poll()
    assert task.progress == 42
    assert app.rearmed is True
