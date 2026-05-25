"""Tests for transcriber._normalize_language.

Regression guard for the silent no-output bug: an auto-transcribe carried
a download's "en-US" subtitle language straight into faster-whisper, which
only accepts ISO-639-1 codes and raised, so no transcript was written.
"""
from __future__ import annotations

import pytest

from core.transcriber import _normalize_language


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("en-US", "en"),    # the exact code that shipped broken
        ("pt-BR", "pt"),
        ("zh-Hans", "zh"),
        ("en_US", "en"),    # underscore variant
        ("EN", "en"),       # case-insensitive
        ("  fr  ", "fr"),   # surrounding whitespace
        ("en", "en"),
        ("fa", "fa"),
        ("yue", "yue"),     # multi-letter code kept
    ],
)
def test_normalize_language_valid(raw, expected):
    assert _normalize_language(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "auto", "xx", "xx-YY", "klingon", "  "])
def test_normalize_language_falls_back_to_autodetect(raw):
    # Unknown / empty -> None so transcribe() auto-detects instead of raising.
    assert _normalize_language(raw) is None
