"""Tests for the SRT / JSON / TXT writers."""
from __future__ import annotations

import json
import math

import pytest

from core.writers import get_writer, supported_formats
from core.writers import json_writer, srt, txt


SAMPLE = [
    {"start": 0.0, "end": 1.5, "text": "Hello world."},
    {"start": 1.5, "end": 3.25, "text": "Second cue."},
    {"start": 3.25, "end": 5.0, "text": "Cue with --> arrow."},
]


def test_supported_formats_list() -> None:
    assert set(supported_formats()) == {"srt", "json", "txt"}


def test_get_writer_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        get_writer("docx")


def test_srt_round_trip_shape() -> None:
    body = srt.write(SAMPLE)
    # 3 cues = 3 numbered blocks. Each block ends in a blank line.
    assert "1\n00:00:00,000 --> 00:00:01,500" in body
    assert "2\n00:00:01,500 --> 00:00:03,250" in body
    assert "3\n00:00:03,250 --> 00:00:05,000" in body
    # The literal --> in payload should be escaped.
    assert "--> arrow" not in body
    assert "→ arrow" in body


def test_srt_nan_clamped_to_zero() -> None:
    body = srt.write([{"start": float("nan"), "end": 1.0, "text": "bad"}])
    assert "00:00:00,000" in body


def test_srt_negative_clamped_to_zero() -> None:
    body = srt.write([{"start": -5.0, "end": 1.0, "text": "neg"}])
    assert "00:00:00,000" in body


def test_json_writer_strict() -> None:
    body = json_writer.write(SAMPLE)
    data = json.loads(body)
    assert len(data) == 3
    assert data[0]["start"] == 0.0
    assert data[0]["end"] == 1.5
    assert data[0]["text"] == "Hello world."


def test_json_writer_nan_becomes_zero() -> None:
    body = json_writer.write([
        {"start": float("inf"), "end": float("nan"), "text": "x"},
    ])
    data = json.loads(body)
    assert math.isfinite(data[0]["start"]) and data[0]["start"] == 0.0
    assert math.isfinite(data[0]["end"]) and data[0]["end"] == 0.0


def test_txt_writer_just_text_lines() -> None:
    body = txt.write(SAMPLE)
    assert body.rstrip("\n").split("\n") == [
        "Hello world.",
        "Second cue.",
        "Cue with --> arrow.",
    ]
