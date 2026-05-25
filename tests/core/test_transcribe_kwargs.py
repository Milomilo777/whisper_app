"""Tests for _build_transcribe_kwargs language handling.

This is the central kwargs builder for the DEFAULT faster-whisper path, so
it must coerce any UI/download language hint into a code faster-whisper
accepts — otherwise a region tag ("en-US") or a multi-value picker code
("zh-Hans,zh-CN") raises ValueError and produces no output.
"""
from __future__ import annotations

from core.task import TranscriptionTask
from core.transcriber import _build_transcribe_kwargs


def _task(language) -> TranscriptionTask:
    t = TranscriptionTask("clip.mp4")
    t.language = language
    return t


def test_region_tag_reduced_to_base():
    assert _build_transcribe_kwargs(_task("en-US")).get("language") == "en"


def test_multivalue_picker_code_reduced_to_base():
    assert _build_transcribe_kwargs(_task("zh-Hans,zh-CN")).get("language") == "zh"
    assert _build_transcribe_kwargs(_task("pt,pt-BR,pt-PT")).get("language") == "pt"


def test_plain_code_passes_through():
    assert _build_transcribe_kwargs(_task("fa")).get("language") == "fa"


def test_language_omitted_when_unset_or_auto():
    # None / "Auto" / unknown all mean auto-detect: no language kwarg at all.
    assert "language" not in _build_transcribe_kwargs(_task(None))
    assert "language" not in _build_transcribe_kwargs(_task("Auto"))
    assert "language" not in _build_transcribe_kwargs(_task("klingon"))
