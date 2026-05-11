"""Tests for ``core.writers`` — every writer takes the same fixture."""
from __future__ import annotations

import json

import pytest

from core.writers import (
    WRITERS,
    get_writer,
    json_writer,
    lrc,
    srt,
    supported_formats,
    tsv,
    txt,
    vtt,
)
from core.writers.base import (
    fmt_lrc_time,
    fmt_srt_time,
    fmt_vtt_time,
    normalize_text,
)


@pytest.fixture
def segments():
    return [
        {"start": 0.0, "end": 1.5, "text": "Hello world"},
        {
            "start": 1.5,
            "end": 3.25,
            "text": "Second   line",
            "words": [
                {"start": 1.5, "end": 2.0, "word": "Second", "probability": 0.9},
                {"start": 2.0, "end": 3.25, "word": "line", "probability": 0.8},
            ],
        },
        {"start": 3.25, "end": 5.0, "text": "Third\tline\nwith\twhitespace"},
    ]


# --- base helpers ---------------------------------------------------------


def test_fmt_srt_time_zero():
    assert fmt_srt_time(0) == "00:00:00,000"


def test_fmt_srt_time_handles_hours():
    assert fmt_srt_time(3661.5) == "01:01:01,500"


def test_fmt_srt_time_negative_clamped():
    assert fmt_srt_time(-0.1) == "00:00:00,000"


def test_fmt_vtt_time_uses_period():
    assert fmt_vtt_time(1.234) == "00:00:01.234"


def test_fmt_lrc_time_format():
    assert fmt_lrc_time(75.5) == "[01:15.50]"


def test_normalize_text_collapses_internal_whitespace():
    assert normalize_text(" hello\t  world\n") == "hello world"


def test_normalize_text_handles_none():
    assert normalize_text("") == ""


# --- writers --------------------------------------------------------------


def test_srt_writer_basic_shape(segments):
    body = srt.write(segments)
    assert body.startswith("1\n")
    assert "00:00:00,000 --> 00:00:01,500" in body
    assert "Hello world" in body
    assert "00:00:03,250 --> 00:00:05,000" in body


def test_srt_writer_segment_count(segments):
    body = srt.write(segments)
    assert body.count(" --> ") == len(segments)


def test_vtt_writer_starts_with_header(segments):
    body = vtt.write(segments)
    assert body.startswith("WEBVTT\n")
    assert " --> " in body


def test_vtt_writer_emits_karaoke_when_words_present(segments):
    body = vtt.write(segments)
    assert "<00:00:01.500><c>Second</c>" in body


def test_tsv_writer_has_header_row(segments):
    body = tsv.write(segments)
    assert body.startswith("start\tend\ttext\n")
    rows = body.strip().split("\n")
    assert len(rows) == 1 + len(segments)


def test_tsv_writer_strips_internal_tabs(segments):
    body = tsv.write(segments)
    data_lines = body.strip().split("\n")[1:]
    for line in data_lines:
        cells = line.split("\t")
        assert len(cells) == 3
        assert "\t" not in cells[2]


def test_txt_writer_one_segment_per_line(segments):
    body = txt.write(segments)
    lines = body.strip().split("\n")
    assert len(lines) == len(segments)
    assert lines[0] == "Hello world"


def test_json_writer_returns_valid_json_list(segments):
    body = json_writer.write(segments)
    parsed = json.loads(body)
    assert isinstance(parsed, list)
    assert len(parsed) == len(segments)
    assert parsed[0]["text"] == "Hello world"


def test_json_writer_preserves_words_when_present(segments):
    parsed = json.loads(json_writer.write(segments))
    assert "words" in parsed[1]
    assert parsed[1]["words"][0]["word"] == "Second"
    assert parsed[1]["words"][0]["probability"] == 0.9


def test_json_writer_omits_words_when_absent(segments):
    parsed = json.loads(json_writer.write(segments))
    assert "words" not in parsed[0]


def test_lrc_writer_uses_audio_file_name(segments):
    body = lrc.write(segments, "/tmp/song.mp3")
    assert body.startswith("[ti:song]")
    assert "[00:00.00]" in body


def test_lrc_writer_no_title_when_path_empty(segments):
    body = lrc.write(segments)
    assert not body.startswith("[ti:")


# --- registry -------------------------------------------------------------


def test_get_writer_returns_callable_for_each_format():
    for name in supported_formats():
        fn = get_writer(name)
        assert callable(fn)


def test_get_writer_is_case_insensitive():
    assert get_writer("SRT") is srt.write
    assert get_writer("Vtt") is vtt.write


def test_get_writer_raises_for_unknown_format():
    with pytest.raises(KeyError):
        get_writer("xml")


def test_supported_formats_includes_canonical_set():
    formats = supported_formats()
    for required in ("srt", "vtt", "tsv", "txt", "json", "lrc"):
        assert required in formats


def test_writers_handle_empty_segment_list():
    for name in supported_formats():
        body = get_writer(name)([])
        assert isinstance(body, str)


def test_srt_writer_uses_comma_decimal():
    body = srt.write([{"start": 0.5, "end": 1.0, "text": "x"}])
    assert "00:00:00,500" in body
    assert "00:00:00.500" not in body
