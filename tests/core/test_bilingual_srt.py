"""Tests for the bilingual SRT writer (core/writers/bilingual_srt.py)."""
from __future__ import annotations

import pytest

from core.writers import bilingual_srt


def _segs():
    return [
        {"start": 0.0, "end": 1.5, "text": "Hello there."},
        {"start": 1.5, "end": 3.0, "text": "How are you?"},
    ]


def test_write_includes_both_languages_per_cue():
    out = bilingual_srt.write(_segs(), ["Bonjour.", "Comment allez-vous?"])
    lines = out.split("\n")
    assert lines[0] == "1"
    assert lines[1] == "00:00:00,000 --> 00:00:01,500"
    assert lines[2] == "Hello there."
    assert lines[3] == "Bonjour."
    assert lines[4] == ""
    assert lines[5] == "2"
    assert "Comment allez-vous?" in out


def test_write_omits_blank_translation_line():
    out = bilingual_srt.write(_segs(), ["Bonjour.", ""])
    blocks = out.strip("\n").split("\n\n")
    # Second cue has only the original line (no trailing blank
    # translation line inflating the block).
    assert blocks[1].split("\n") == [
        "2",
        "00:00:01,500 --> 00:00:03,000",
        "How are you?",
    ]


def test_write_raises_on_length_mismatch():
    with pytest.raises(ValueError, match="must match"):
        bilingual_srt.write(_segs(), ["only one"])


def test_write_prefixes_speaker_on_original_line_only():
    segs = [{"start": 0.0, "end": 1.0, "text": "Hi.", "speaker": "Speaker 1"}]
    out = bilingual_srt.write(segs, ["Salut."])
    lines = out.split("\n")
    assert lines[2] == "Speaker 1: Hi."
    assert lines[3] == "Salut."


def test_write_escapes_cue_separator_in_both_languages():
    segs = [{"start": 0.0, "end": 1.0, "text": "a --> b"}]
    out = bilingual_srt.write(segs, ["c --> d"])
    assert "-->" not in out.split("\n", 2)[2]  # only the timecode line keeps it
    assert "a → b" in out
    assert "c → d" in out


def test_write_empty_segments_and_translations():
    assert bilingual_srt.write([], []) == ""
