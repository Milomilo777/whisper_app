"""Extended coverage for ``core.task.TranscriptionTask``."""
from __future__ import annotations

import pytest

from core.task import TranscriptionTask


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/file.mp3",
        "C:\\Users\\me\\file.mp4",
        "relative.wav",
        "with spaces.flac",
        "with(parens).m4a",
        "with视频.mp4",
        "with🎬.mp4",
        "",
        "/very/long/" + ("x" * 500) + ".mp3",
        "//unc/share/file.wav",
        "C:/forward/slash.mp3",
    ],
)
def test_task_accepts_any_string_path(path: str) -> None:
    t = TranscriptionTask(path)
    assert t.file_path == path


def test_task_initial_status_waiting() -> None:
    t = TranscriptionTask("/x.mp3")
    assert t.status == "waiting"


def test_task_initial_progress_zero() -> None:
    t = TranscriptionTask("/x.mp3")
    assert t.progress == 0


def test_task_initial_start_time_none() -> None:
    t = TranscriptionTask("/x.mp3")
    assert t.start_time is None


def test_task_initial_end_time_none() -> None:
    t = TranscriptionTask("/x.mp3")
    assert t.end_time is None


def test_task_initial_cancelled_false() -> None:
    t = TranscriptionTask("/x.mp3")
    assert t.cancelled is False


def test_task_initial_detected_language_empty() -> None:
    t = TranscriptionTask("/x.mp3")
    assert t.detected_language == ""


def test_task_initial_language_probability_zero() -> None:
    t = TranscriptionTask("/x.mp3")
    assert t.language_probability == 0.0


def test_task_initial_error_message_empty() -> None:
    t = TranscriptionTask("/x.mp3")
    assert t.error_message == ""


@pytest.mark.parametrize(
    "new_status",
    ["running", "finished", "cancelled", "error", "waiting", "any-string"],
)
def test_task_status_mutable(new_status: str) -> None:
    t = TranscriptionTask("/x.mp3")
    t.status = new_status
    assert t.status == new_status


@pytest.mark.parametrize("progress", [0, 1, 50, 99, 100, 150, -10])
def test_task_progress_mutable(progress: int) -> None:
    t = TranscriptionTask("/x.mp3")
    t.progress = progress
    assert t.progress == progress


@pytest.mark.parametrize("ts", [None, 0.0, 1000.0, 1_700_000_000.0])
def test_task_start_time_mutable(ts: float | None) -> None:
    t = TranscriptionTask("/x.mp3")
    t.start_time = ts
    assert t.start_time == ts


@pytest.mark.parametrize("ts", [None, 0.0, 1000.0, 1_700_000_000.0])
def test_task_end_time_mutable(ts: float | None) -> None:
    t = TranscriptionTask("/x.mp3")
    t.end_time = ts
    assert t.end_time == ts


def test_task_cancelled_mutable_true() -> None:
    t = TranscriptionTask("/x.mp3")
    t.cancelled = True
    assert t.cancelled is True


def test_task_cancelled_mutable_back_to_false() -> None:
    t = TranscriptionTask("/x.mp3")
    t.cancelled = True
    t.cancelled = False
    assert t.cancelled is False


@pytest.mark.parametrize(
    "lang", ["en", "fa", "zh", "ja", "ar", "fr", "de", "es", "ru", ""],
)
def test_task_detected_language_mutable(lang: str) -> None:
    t = TranscriptionTask("/x.mp3")
    t.detected_language = lang
    assert t.detected_language == lang


@pytest.mark.parametrize("p", [0.0, 0.1, 0.5, 0.92, 0.99, 1.0])
def test_task_language_probability_mutable(p: float) -> None:
    t = TranscriptionTask("/x.mp3")
    t.language_probability = p
    assert t.language_probability == p


@pytest.mark.parametrize(
    "msg",
    [
        "",
        "short",
        "x" * 1000,
        "with unicode 视频",
        "with newline\nhere",
    ],
)
def test_task_error_message_mutable(msg: str) -> None:
    t = TranscriptionTask("/x.mp3")
    t.error_message = msg
    assert t.error_message == msg


def test_task_worker_attaches_language_attribute() -> None:
    """The worker uses setattr(task, 'language', ...); attribute must
    not collide with a slot."""
    t = TranscriptionTask("/x.mp3")
    setattr(t, "language", "fa")
    assert getattr(t, "language") == "fa"


def test_task_full_lifecycle_mutation() -> None:
    """Set every field, verify they all stick (no slot interference)."""
    t = TranscriptionTask("/x.mp3")
    t.status = "running"
    t.progress = 42
    t.start_time = 1.0
    t.end_time = 2.0
    t.cancelled = False
    t.detected_language = "fa"
    t.language_probability = 0.95
    t.error_message = ""
    assert (
        t.status,
        t.progress,
        t.start_time,
        t.end_time,
        t.cancelled,
        t.detected_language,
        t.language_probability,
    ) == ("running", 42, 1.0, 2.0, False, "fa", 0.95)


def test_task_two_instances_independent() -> None:
    """Each TranscriptionTask is its own object — mutating one doesn't
    leak into the other (no class-level mutable state)."""
    a = TranscriptionTask("/a.mp3")
    b = TranscriptionTask("/b.mp3")
    a.status = "running"
    a.progress = 50
    assert b.status == "waiting"
    assert b.progress == 0
