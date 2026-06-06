"""Hermetic tests for the R2 download pause/resume state transitions.

Downloads only had Cancel before R2. yt-dlp has no live pause signal, so
"pause" is STOP-AND-CONTINUE: tear the process down (same kill path as
cancel) but land on status "paused", keep the partial .part, and let a
later "resume" re-enqueue the SAME task so yt-dlp continues via -c/--continue.

These call the App methods UNBOUND against a lightweight fake ``self`` so we
exercise the real status-flip logic with NO Tk root (the Python-3.14 box
intermittently can't build a real tk.Tk(), and constructing one here would
be both flaky and unnecessary — this is pure orchestration logic).
"""
from __future__ import annotations

import types

import pytest

pytest.importorskip("tkinter")

from app.app import App
from app.domain.tasks import VideoDownloadTask


def _dl_task(status: str = "running", smtv: bool = False) -> VideoDownloadTask:
    fmt = {
        "mode": "Audio and video",
        "output": "mp4",
        "audio": {"kind": "smtv" if smtv else "best_audio"},
        "video": {"kind": "smtv" if smtv else "best_video"},
    }
    t = VideoDownloadTask(
        url="https://example.com/v", folder="/tmp", format_label="x",
        format_info=fmt,
    )
    t.status = status
    return t


def _fake_app(task: VideoDownloadTask):
    """A minimal stand-in carrying just what pause/resume_download touch."""
    calls: dict[str, int] = {"refresh": 0, "process_queue": 0, "log": 0}

    def _refresh() -> None:
        calls["refresh"] += 1

    def _process_queue() -> None:
        calls["process_queue"] += 1

    def _log(_msg: str) -> None:
        calls["log"] += 1

    app = types.SimpleNamespace(
        download_current=task,
        download_queue=[task],
        refresh_download_queue=_refresh,
        download_service=types.SimpleNamespace(process_queue=_process_queue),
        log=_log,
        _calls=calls,
    )
    return app


# --- pause_download --------------------------------------------------------


def test_pause_download_flips_running_to_paused_and_keeps_partial():
    task = _dl_task("running")
    task.process = None  # no live process in this unit context
    app = _fake_app(task)

    App.pause_download(app, task)  # type: ignore[arg-type]

    assert task.status == "paused"
    assert task.paused is True
    assert task.cancelled is False           # NOT a cancel — partial is kept
    assert task.end_time is not None         # Elapsed frozen at the hold
    assert app.download_current is None       # released the single slot
    assert app._calls["process_queue"] == 1   # next waiting download may start


def test_pause_download_ignores_terminal_status():
    for status in ("finished", "cancelled", "error", "paused"):
        task = _dl_task(status)
        task.process = None
        app = _fake_app(task)
        App.pause_download(app, task)  # type: ignore[arg-type]
        # No transition: a finished/cancelled/etc download can't be paused.
        assert task.status == status
        assert task.paused is False


def test_pause_download_ignores_waiting():
    # A not-yet-started "waiting" download has no process to stop-and-continue;
    # pausing it would only strand it in "paused" (the action bar offers Cancel
    # for waiting rows, not Pause). Only a RUNNING download can be paused.
    task = _dl_task("waiting")
    task.process = None
    app = _fake_app(task)
    App.pause_download(app, task)  # type: ignore[arg-type]
    assert task.status == "waiting"
    assert task.paused is False
    assert app._calls["process_queue"] == 0


def test_pause_download_refuses_smtv():
    task = _dl_task("running", smtv=True)
    task.process = None
    app = _fake_app(task)

    App.pause_download(app, task)  # type: ignore[arg-type]

    # SMTV has no resume point — left running, a log line explains why.
    assert task.status == "running"
    assert task.paused is False
    assert app._calls["log"] == 1


# --- resume_download -------------------------------------------------------


def test_resume_download_reenqueues_same_task():
    task = _dl_task("paused")
    task.paused = True
    task.end_time = 123.0
    # Simulate the paused task already removed from the active queue.
    app = _fake_app(task)
    app.download_queue = []

    App.resume_download(app, task)  # type: ignore[arg-type]

    assert task.status == "waiting"        # re-dispatched, not a fresh task
    assert task.paused is False
    assert task.cancelled is False
    assert task.end_time is None           # Elapsed counter restarts
    assert task in app.download_queue      # re-enqueued the SAME object
    assert app._calls["process_queue"] == 1


def test_resume_download_keeps_existing_queue_membership():
    task = _dl_task("paused")
    task.paused = True
    app = _fake_app(task)            # task already in download_queue

    App.resume_download(app, task)  # type: ignore[arg-type]

    # No duplicate row when the task was never removed from the queue.
    assert app.download_queue.count(task) == 1


def test_resume_download_ignores_non_paused():
    for status in ("running", "finished", "cancelled", "error", "waiting"):
        task = _dl_task(status)
        app = _fake_app(task)
        App.resume_download(app, task)  # type: ignore[arg-type]
        assert task.status == status
        assert app._calls["process_queue"] == 0


# --- the pause -> resume round-trip preserves task identity ----------------


def test_pause_then_resume_round_trip():
    task = _dl_task("running")
    task.process = None
    app = _fake_app(task)

    App.pause_download(app, task)   # type: ignore[arg-type]
    assert task.status == "paused"

    App.resume_download(app, task)  # type: ignore[arg-type]
    assert task.status == "waiting"
    assert task.paused is False
    # Same object travels the whole way — that's what lets yt-dlp's
    # -c/--continue pick up the existing .part instead of restarting.
    assert task in app.download_queue


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
