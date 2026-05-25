"""Tests for the auto-transcribe-after-download glue.

Doesn't spawn yt-dlp — fakes the App + service interactions so the wiring
in DownloadService._finish() is exercised.
"""
from __future__ import annotations

import types

from app.services.download_service import DownloadService


class _FakeApp:
    def __init__(self, *, auto: bool):
        self.app_config = {"auto_transcribe_after_download": auto}
        self.download_queue: list = []
        self.download_current = None
        self.history = None
        self.enqueued: list[tuple[str, str]] = []
        self.enqueued_sources: list = []
        self.logs: list[str] = []
        self.refresh_called = 0

    def enqueue_transcription_from_download(
        self, file_path: str, language: str, source_download: object = None
    ) -> None:
        self.enqueued.append((file_path, language))
        self.enqueued_sources.append(source_download)

    def log(self, msg: str) -> None:
        self.logs.append(msg)

    def refresh_download_queue(self) -> None:
        self.refresh_called += 1


def _task(detected_language: str = "en") -> object:
    return types.SimpleNamespace(
        url="https://x", folder="/tmp", format_label="mp4 video",
        format_info={}, title="T",
        subtitles_enabled=False, subtitle_lang="",
        detected_language=detected_language,
        process=None, status="running", progress=0, start_time=0.0,
        cancelled=False, history_id=0,
    )


def test_finish_enqueues_when_flag_on():
    app = _FakeApp(auto=True)
    svc = DownloadService(app)  # type: ignore[arg-type]
    task = _task()
    svc._finish(task, "finished", saved_path="/tmp/T.mp4")
    assert app.enqueued == [("/tmp/T.mp4", "en")]
    # The download row is linked to its transcription and flipped to
    # "transcribing" so the user sees work continue after the download.
    assert app.enqueued_sources == [task]
    assert task.status == "transcribing"
    assert any("transcrib" in m.lower() for m in app.logs)


def test_finish_skips_when_flag_off():
    app = _FakeApp(auto=False)
    svc = DownloadService(app)  # type: ignore[arg-type]
    task = _task()
    svc._finish(task, "finished", saved_path="/tmp/T.mp4")
    assert app.enqueued == []


def test_finish_skips_when_no_saved_path():
    app = _FakeApp(auto=True)
    svc = DownloadService(app)  # type: ignore[arg-type]
    task = _task()
    svc._finish(task, "finished", saved_path=None)
    assert app.enqueued == []


def test_finish_skips_when_status_is_error():
    app = _FakeApp(auto=True)
    svc = DownloadService(app)  # type: ignore[arg-type]
    task = _task()
    svc._finish(task, "error", saved_path="/tmp/T.mp4")
    assert app.enqueued == []


def test_finish_clears_download_current():
    app = _FakeApp(auto=False)
    task = _task()
    app.download_current = task
    svc = DownloadService(app)  # type: ignore[arg-type]
    svc._finish(task, "finished", saved_path=None)
    assert app.download_current is None


def test_finish_passes_detected_language_to_enqueue():
    app = _FakeApp(auto=True)
    svc = DownloadService(app)  # type: ignore[arg-type]
    task = _task(detected_language="fa")
    svc._finish(task, "finished", saved_path="/tmp/T.mp4")
    assert app.enqueued == [("/tmp/T.mp4", "fa")]
