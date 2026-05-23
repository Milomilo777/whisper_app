"""Tests for the tiny ``TranscriptionTask`` model."""
from __future__ import annotations

from core.task import TranscriptionTask


def test_initial_state() -> None:
    t = TranscriptionTask("/tmp/file.mp3")
    assert t.file_path == "/tmp/file.mp3"
    assert t.status == "waiting"
    assert t.progress == 0
    assert t.cancelled is False
    assert t.start_time is None
    assert t.end_time is None
    assert t.detected_language == ""
    assert t.language_probability == 0.0
    assert t.error_message == ""


def test_fields_are_mutable() -> None:
    t = TranscriptionTask("/tmp/x.wav")
    t.status = "running"
    t.progress = 42
    t.cancelled = True
    t.detected_language = "en"
    t.language_probability = 0.92
    t.error_message = "something"
    assert t.status == "running"
    assert t.progress == 42
    assert t.cancelled is True
    assert t.detected_language == "en"
    assert t.language_probability == 0.92
    assert t.error_message == "something"
