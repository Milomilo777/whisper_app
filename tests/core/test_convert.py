"""Tests for ``core.convert`` — transcript format conversion.

Round-trips SRT / VTT / TSV / JSON into the universal segment list and back
out via the writers registry, plus the .otr import and graceful handling of
bad / empty / output-only (.txt) input.
"""
from __future__ import annotations

import json

import pytest

from core import convert
from core.integrations import otranscribe


# --- parse round-trips ------------------------------------------------------

SRT_SAMPLE = (
    "1\n"
    "00:00:01,000 --> 00:00:03,500\n"
    "Hello world\n"
    "\n"
    "2\n"
    "00:00:03,500 --> 00:00:06,000\n"
    "Second line\n"
)

VTT_SAMPLE = (
    "WEBVTT\n"
    "\n"
    "00:00:01.000 --> 00:00:03.500\n"
    "Hello world\n"
    "\n"
    "00:00:03.500 --> 00:00:06.000\n"
    "Second line\n"
)

TSV_SAMPLE = (
    "start\tend\ttext\n"
    "1000\t3500\tHello world\n"
    "3500\t6000\tSecond line\n"
)

JSON_SAMPLE = json.dumps(
    [
        {"start": 1.0, "end": 3.5, "text": "Hello world"},
        {"start": 3.5, "end": 6.0, "text": "Second line"},
    ]
)


@pytest.mark.parametrize(
    "ext,content",
    [
        ("srt", SRT_SAMPLE),
        ("vtt", VTT_SAMPLE),
        ("tsv", TSV_SAMPLE),
        ("json", JSON_SAMPLE),
    ],
)
def test_parse_to_segments_structure(tmp_path, ext, content):
    p = tmp_path / f"sample.{ext}"
    p.write_text(content, encoding="utf-8")
    segs = convert.parse_to_segments(str(p))
    assert len(segs) == 2
    assert segs[0]["start"] == pytest.approx(1.0)
    assert segs[0]["end"] == pytest.approx(3.5)
    assert segs[0]["text"] == "Hello world"
    assert segs[1]["text"] == "Second line"
    assert segs[1]["end"] == pytest.approx(6.0)


@pytest.mark.parametrize("ext,content", [
    ("srt", SRT_SAMPLE), ("vtt", VTT_SAMPLE),
    ("tsv", TSV_SAMPLE), ("json", JSON_SAMPLE),
])
def test_convert_to_srt(tmp_path, ext, content):
    p = tmp_path / f"sample.{ext}"
    p.write_text(content, encoding="utf-8")
    out = convert.convert_file(str(p), "srt")
    assert out.endswith(".srt")
    body = open(out, encoding="utf-8").read()
    assert "Hello world" in body
    assert "00:00:01,000 --> 00:00:03,500" in body
    # Re-parsing the emitted SRT yields the same two segments.
    assert len(convert.parse_to_segments(out)) == 2


@pytest.mark.parametrize("ext,content", [
    ("srt", SRT_SAMPLE), ("vtt", VTT_SAMPLE),
    ("tsv", TSV_SAMPLE), ("json", JSON_SAMPLE),
])
def test_convert_to_json(tmp_path, ext, content):
    p = tmp_path / f"sample.{ext}"
    p.write_text(content, encoding="utf-8")
    out = convert.convert_file(str(p), "json")
    data = json.loads(open(out, encoding="utf-8").read())
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["text"] == "Hello world"
    assert data[0]["start"] == pytest.approx(1.0)


def test_convert_same_format_does_not_clobber_source(tmp_path):
    p = tmp_path / "sample.srt"
    p.write_text(SRT_SAMPLE, encoding="utf-8")
    out = convert.convert_file(str(p), "srt")
    # In-place re-emit must NOT overwrite the source.
    assert out != str(p)
    assert ".converted" in out
    assert p.read_text(encoding="utf-8") == SRT_SAMPLE


def test_otr_is_a_convert_target():
    assert "otr" in convert.CONVERT_TARGETS


@pytest.mark.parametrize("ext,content", [
    ("srt", SRT_SAMPLE), ("vtt", VTT_SAMPLE),
    ("tsv", TSV_SAMPLE), ("json", JSON_SAMPLE),
])
def test_convert_to_otr(tmp_path, ext, content):
    p = tmp_path / f"sample.{ext}"
    p.write_text(content, encoding="utf-8")
    out = convert.convert_file(str(p), "otr")
    assert out.endswith(".otr")
    payload = json.loads(open(out, encoding="utf-8").read())
    assert set(payload.keys()) == {"text", "media", "media-source", "media-time"}
    assert "Hello world" in payload["text"]
    # Re-parsing the emitted .otr recovers both segments.
    assert len(convert.parse_to_segments(out)) == 2


def test_explicit_out_path(tmp_path):
    p = tmp_path / "sample.json"
    p.write_text(JSON_SAMPLE, encoding="utf-8")
    target = tmp_path / "out" / "result.vtt"
    out = convert.convert_file(str(p), "vtt", str(target))
    assert out == str(target)
    body = target.read_text(encoding="utf-8")
    assert body.startswith("WEBVTT")


# --- .otr import ------------------------------------------------------------

def test_otr_import(tmp_path):
    # Build an .otr from a known SRT via the existing helper, then parse it.
    srt = tmp_path / "src.srt"
    srt.write_text(SRT_SAMPLE, encoding="utf-8")
    otr_text = otranscribe.srt_to_otr(str(srt), media_filename="src.mp4")
    otr = tmp_path / "src.otr"
    otr.write_text(otr_text, encoding="utf-8")

    segs = convert.parse_to_segments(str(otr))
    assert len(segs) == 2
    assert segs[0]["text"] == "Hello world"
    # .otr -> srt convert works end to end.
    out = convert.convert_file(str(otr), "srt")
    assert "Hello world" in open(out, encoding="utf-8").read()


# --- bad / empty / output-only input ----------------------------------------

def test_txt_is_output_only(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("just some text\nno timestamps\n", encoding="utf-8")
    with pytest.raises(convert.ConvertError):
        convert.parse_to_segments(str(p))


def test_missing_file(tmp_path):
    with pytest.raises(convert.ConvertError):
        convert.parse_to_segments(str(tmp_path / "nope.srt"))


def test_empty_file(tmp_path):
    p = tmp_path / "empty.srt"
    p.write_text("", encoding="utf-8")
    # An empty SRT is a valid-but-cue-less file: zero segments, no crash.
    assert convert.parse_to_segments(str(p)) == []


def test_empty_unknown_extension_raises(tmp_path):
    p = tmp_path / "empty.dat"
    p.write_text("", encoding="utf-8")
    with pytest.raises(convert.ConvertError):
        convert.parse_to_segments(str(p))


def test_bad_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(convert.ConvertError):
        convert.parse_to_segments(str(p))


def test_unknown_output_format(tmp_path):
    p = tmp_path / "sample.srt"
    p.write_text(SRT_SAMPLE, encoding="utf-8")
    with pytest.raises(convert.ConvertError):
        convert.convert_file(str(p), "docx")  # binary writer, not offered
    with pytest.raises(convert.ConvertError):
        convert.convert_file(str(p), "bogus")


def test_content_sniff_no_extension(tmp_path):
    # No / unknown extension: detect by content.
    p = tmp_path / "noext"
    p.write_text(SRT_SAMPLE, encoding="utf-8")
    segs = convert.parse_to_segments(str(p))
    assert len(segs) == 2
