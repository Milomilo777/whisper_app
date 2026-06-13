"""Tests for the three new transcript formats: ELAN, InqScribe, Express Scribe.

ELAN (.eaf) and InqScribe are bidirectional (write + parse, wired into
``core.convert``); Express Scribe is EXPORT-ONLY (whole-second ``[hh:mm:ss]``
cues are too lossy to round-trip, so it is intentionally absent from
``core.convert.PARSE_FORMATS``).
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from core import convert
from core.writers import elan, express_scribe, inqscribe

SEGMENTS = [
    {"start": 1.0, "end": 3.5, "text": "Hello world"},
    {"start": 3.5, "end": 6.25, "text": "Second line"},
]


# --- ELAN (.eaf) --------------------------------------------------------------

def test_elan_write_is_valid_xml_with_expected_tags():
    body = elan.write(SEGMENTS)
    root = ET.fromstring(body)
    assert root.tag == "ANNOTATION_DOCUMENT"

    slots = list(root.iter("TIME_SLOT"))
    assert len(slots) == 4  # one start + one end per segment
    # Millisecond TIME_VALUEs.
    values = {s.get("TIME_SLOT_ID"): s.get("TIME_VALUE") for s in slots}
    assert "1000" in values.values()
    assert "3500" in values.values()
    assert "6250" in values.values()

    annotations = list(root.iter("ALIGNABLE_ANNOTATION"))
    assert len(annotations) == 2
    texts = [
        (a.find("ANNOTATION_VALUE").text or "")
        for a in annotations
    ]
    assert texts == ["Hello world", "Second line"]

    tiers = list(root.iter("TIER"))
    assert len(tiers) == 1


def test_elan_round_trip_via_convert(tmp_path):
    body = elan.write(SEGMENTS)
    p = tmp_path / "sample.eaf"
    p.write_text(body, encoding="utf-8")

    segs = convert.parse_to_segments(str(p))
    assert len(segs) == 2
    assert segs[0]["text"] == "Hello world"
    assert segs[0]["start"] == pytest.approx(1.0)
    assert segs[0]["end"] == pytest.approx(3.5)
    assert segs[1]["text"] == "Second line"
    assert segs[1]["start"] == pytest.approx(3.5)
    assert segs[1]["end"] == pytest.approx(6.25)


def test_elan_is_in_parse_and_output_formats():
    assert "elan" in convert.PARSE_FORMATS
    assert "elan" in convert.OUTPUT_FORMATS


def test_elan_convert_file_default_extension(tmp_path):
    import json

    src = tmp_path / "sample.json"
    src.write_text(json.dumps(SEGMENTS), encoding="utf-8")
    out = convert.convert_file(str(src), "elan")
    assert out.endswith(".eaf")
    assert len(convert.parse_to_segments(out)) == 2


def test_elan_skips_annotation_with_missing_slot(tmp_path):
    # A malformed .eaf referencing a non-existent slot is skipped, not fatal.
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<ANNOTATION_DOCUMENT>'
        '<TIME_ORDER>'
        '<TIME_SLOT TIME_SLOT_ID="ts1" TIME_VALUE="1000"/>'
        '<TIME_SLOT TIME_SLOT_ID="ts2" TIME_VALUE="2000"/>'
        '</TIME_ORDER>'
        '<TIER TIER_ID="default">'
        '<ANNOTATION><ALIGNABLE_ANNOTATION ANNOTATION_ID="a1" '
        'TIME_SLOT_REF1="ts1" TIME_SLOT_REF2="ts2">'
        '<ANNOTATION_VALUE>ok</ANNOTATION_VALUE></ALIGNABLE_ANNOTATION></ANNOTATION>'
        '<ANNOTATION><ALIGNABLE_ANNOTATION ANNOTATION_ID="a2" '
        'TIME_SLOT_REF1="ts1" TIME_SLOT_REF2="ts99">'
        '<ANNOTATION_VALUE>missing slot</ANNOTATION_VALUE></ALIGNABLE_ANNOTATION></ANNOTATION>'
        '</TIER>'
        '</ANNOTATION_DOCUMENT>'
    )
    p = tmp_path / "broken.eaf"
    p.write_text(body, encoding="utf-8")
    segs = convert.parse_to_segments(str(p))
    assert len(segs) == 1
    assert segs[0]["text"] == "ok"


def test_elan_invalid_xml_raises(tmp_path):
    p = tmp_path / "bad.eaf"
    p.write_text("<not valid xml", encoding="utf-8")
    with pytest.raises(convert.ConvertError):
        convert.parse_to_segments(str(p))


# --- InqScribe -----------------------------------------------------------------

def test_inqscribe_write_format():
    body = inqscribe.write(SEGMENTS)
    lines = body.strip().split("\n")
    assert lines[0] == "[00:00:01.00]Hello world"
    assert lines[1] == "[00:00:03.50]Second line"


def test_inqscribe_round_trip_via_convert(tmp_path):
    body = inqscribe.write(SEGMENTS)
    p = tmp_path / "sample.inqscr"
    p.write_text(body, encoding="utf-8")

    segs = convert.parse_to_segments(str(p))
    assert len(segs) == 2
    assert segs[0]["text"] == "Hello world"
    assert segs[0]["start"] == pytest.approx(1.0)
    assert segs[0]["end"] == pytest.approx(3.5)
    assert segs[1]["text"] == "Second line"
    assert segs[1]["start"] == pytest.approx(3.5)
    # Last segment has no following cue: end = start + 5.0 default.
    assert segs[1]["end"] == pytest.approx(8.5)


def test_inqscribe_is_in_parse_and_output_formats():
    assert "inqscribe" in convert.PARSE_FORMATS
    assert "inqscribe" in convert.OUTPUT_FORMATS


def test_inqscribe_convert_file_default_extension(tmp_path):
    import json

    src = tmp_path / "sample.json"
    src.write_text(json.dumps(SEGMENTS), encoding="utf-8")
    out = convert.convert_file(str(src), "inqscribe")
    assert out.endswith(".inqscr")
    assert len(convert.parse_to_segments(out)) == 2


def test_inqscribe_txt_content_sniff(tmp_path):
    # A .txt with InqScribe-style timestamps is detected as inqscribe, not
    # rejected as the timestamp-less output-only TXT.
    body = inqscribe.write(SEGMENTS)
    p = tmp_path / "sample.txt"
    p.write_text(body, encoding="utf-8")
    segs = convert.parse_to_segments(str(p))
    assert len(segs) == 2
    assert segs[0]["text"] == "Hello world"


# --- Express Scribe (export-only) ----------------------------------------------

def test_express_scribe_write_format():
    body = express_scribe.write(SEGMENTS)
    lines = body.strip().split("\n")
    assert lines[0] == "[00:00:01] Hello world"
    assert lines[1] == "[00:00:04] Second line"


def test_express_scribe_is_output_only():
    assert "express_scribe" in convert.OUTPUT_FORMATS
    assert "express_scribe" not in convert.PARSE_FORMATS


def test_express_scribe_convert_file(tmp_path):
    import json

    src = tmp_path / "sample.json"
    src.write_text(json.dumps(SEGMENTS), encoding="utf-8")
    out = convert.convert_file(str(src), "express_scribe")
    assert out.endswith(".txt")
    body = open(out, encoding="utf-8").read()
    assert "[00:00:01] Hello world" in body
    assert "[00:00:04] Second line" in body


# --- speaker labels --------------------------------------------------------------

def test_speaker_prefix_carried_through():
    segs = [{"start": 0.0, "end": 1.0, "text": "hi", "speaker": "Speaker 1"}]
    assert "Speaker 1: hi" in elan.write(segs)
    assert "Speaker 1: hi" in inqscribe.write(segs)
    assert "Speaker 1: hi" in express_scribe.write(segs)
