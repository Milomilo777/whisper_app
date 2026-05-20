"""Tests for ``core.writers`` — every writer takes the same fixture."""
from __future__ import annotations

import json

import pytest

from core.writers import (
    BINARY_WRITERS,
    WRITERS,
    docx_writer,
    get_binary_writer,
    get_writer,
    is_binary,
    json_writer,
    lrc,
    md,
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
        fn = get_binary_writer(name) if is_binary(name) else get_writer(name)
        assert callable(fn)


def test_get_writer_is_case_insensitive():
    assert get_writer("SRT") is srt.write
    assert get_writer("Vtt") is vtt.write


def test_get_writer_raises_for_unknown_format():
    with pytest.raises(KeyError):
        get_writer("xml")


def test_supported_formats_includes_canonical_set():
    formats = supported_formats()
    for required in ("srt", "vtt", "tsv", "txt", "json", "lrc", "md", "docx"):
        assert required in formats


def test_writers_handle_empty_segment_list():
    for name in supported_formats():
        if is_binary(name):
            payload = get_binary_writer(name)([], "")
            assert isinstance(payload, (bytes, bytearray))
        else:
            body = get_writer(name)([], "")
            assert isinstance(body, str)


def test_srt_writer_uses_comma_decimal():
    body = srt.write([{"start": 0.5, "end": 1.0, "text": "x"}])
    assert "00:00:00,500" in body
    assert "00:00:00.500" not in body


def test_srt_writer_prepends_speaker_when_present():
    body = srt.write([
        {"start": 0.0, "end": 1.0, "text": "alpha", "speaker": "Speaker 00"},
        {"start": 1.0, "end": 2.0, "text": "beta"},  # no speaker
    ])
    assert "Speaker 00: alpha" in body
    # The unlabeled segment stays clean — no stray "Speaker" prefix.
    lines = body.splitlines()
    beta_line = next(ln for ln in lines if ln == "beta")
    assert beta_line == "beta"


def test_json_writer_includes_speaker_when_present():
    body = json_writer.write([
        {"start": 0.0, "end": 1.0, "text": "alpha", "speaker": "Speaker 00"},
        {"start": 1.0, "end": 2.0, "text": "beta"},
    ])
    payload = json.loads(body)
    assert payload[0]["speaker"] == "Speaker 00"
    assert "speaker" not in payload[1]


# --- Markdown writer ------------------------------------------------------


def test_md_writer_has_heading_and_timestamps(segments):
    body = md.write(segments, "interview.mp3")
    assert body.startswith("# interview.mp3")
    assert "**00:00:00**" in body
    assert "**00:00:01**" in body  # second segment starts at 1.5s
    assert "Hello world" in body
    assert "Second line" in body


def test_md_writer_includes_speaker_label_when_present():
    body = md.write([
        {"start": 0.0, "end": 1.0, "text": "hi", "speaker": "Speaker 1"},
        {"start": 1.0, "end": 2.0, "text": "yo", "speaker": "Speaker 2"},
    ], "x.wav")
    assert "_Speaker 1:_" in body
    assert "_Speaker 2:_" in body


def test_md_writer_omits_speaker_when_absent():
    body = md.write([{"start": 0.0, "end": 1.0, "text": "hi"}], "x.wav")
    assert "_" not in body.replace("\n", "")  # no italic markers


def test_md_writer_skips_empty_segments():
    body = md.write([
        {"start": 0.0, "end": 1.0, "text": "  "},
        {"start": 1.0, "end": 2.0, "text": "real"},
    ], "x.wav")
    assert body.count("**") == 2  # only one segment timestamp -> one pair of **


# --- DOCX writer ----------------------------------------------------------


def test_docx_writer_returns_zip_bytes(segments):
    payload = docx_writer.write_bytes(segments, "meeting.mp4")
    assert isinstance(payload, bytes)
    # DOCX is a ZIP archive; magic bytes are "PK\x03\x04".
    assert payload[:4] == b"PK\x03\x04", payload[:8]
    # Should be substantially larger than the smallest possible zip
    # (the docx skeleton itself runs ~ 20 KB minimum).
    assert len(payload) > 5_000


def test_docx_writer_embeds_segment_text_and_speaker(segments, tmp_path):
    # Round-trip through python-docx: read the zip back and confirm
    # the segment text + speaker actually landed in document.xml.
    import zipfile

    enriched = [
        {"start": 0.0, "end": 1.0, "text": "hello", "speaker": "Alice"},
        {"start": 1.0, "end": 2.0, "text": "world", "speaker": "Bob"},
    ]
    payload = docx_writer.write_bytes(enriched, "x.wav")
    docx_path = tmp_path / "out.docx"
    docx_path.write_bytes(payload)

    with zipfile.ZipFile(docx_path) as zf:
        with zf.open("word/document.xml") as f:
            document_xml = f.read().decode("utf-8")

    assert "hello" in document_xml
    assert "world" in document_xml
    assert "Alice" in document_xml
    assert "Bob" in document_xml
    # Heading should carry the audio basename
    assert "x.wav" in document_xml
    # Timestamps appear in [HH:MM:SS] form
    assert "[00:00:00]" in document_xml
    assert "[00:00:01]" in document_xml


def test_docx_writer_handles_empty_segments_gracefully():
    payload = docx_writer.write_bytes([], "")
    assert payload[:4] == b"PK\x03\x04"


def test_is_binary_table():
    assert is_binary("docx") is True
    assert is_binary("DOCX") is True  # case-insensitive
    for name in ("srt", "vtt", "tsv", "txt", "json", "lrc", "md"):
        assert is_binary(name) is False


def test_binary_writers_registry_only_contains_docx():
    assert set(BINARY_WRITERS.keys()) == {"docx"}
