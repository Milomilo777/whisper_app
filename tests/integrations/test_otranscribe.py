"""Tests for core.integrations.otranscribe."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Make the project root importable when run via plain `pytest` from anywhere.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.integrations.otranscribe import (  # noqa: E402
    fmt_otr_time,
    otr_to_srt,
    segments_to_otr,
    srt_to_otr,
    whisper_json_to_otr,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_otr_text(otr_string: str):
    return json.loads(otr_string)["text"]


def test_fmt_otr_time():
    assert fmt_otr_time(3.456) == "0:03"
    assert fmt_otr_time(63) == "1:03"
    assert fmt_otr_time(3723) == "1:02:03"
    assert fmt_otr_time(0) == "0:00"


def test_srt_to_otr_smoke():
    out = srt_to_otr(str(FIXTURES / "sample.srt"), "interview-01.mp3")
    payload = json.loads(out)
    assert set(payload.keys()) == {"text", "media", "media-source", "media-time"}
    assert payload["media"] == "interview-01.mp3"
    assert payload["media-source"] == ""
    assert payload["media-time"] == 0.0
    assert "\n" not in payload["text"]
    assert payload["text"].count('<span class="timestamp"') == 4


def _round_trip_segments(srt_path: Path):
    otr_string = srt_to_otr(str(srt_path), "audio.wav")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".otr", delete=False
    ) as tmp:
        tmp.write(otr_string)
        otr_path = tmp.name
    try:
        srt_back = otr_to_srt(otr_path)
    finally:
        os.unlink(otr_path)
    # Re-parse both into (start, body) pairs for comparison.
    from core.integrations.otranscribe import _parse_srt as _ps  # noqa: E402

    original = list(_ps(srt_path.read_text(encoding="utf-8-sig")))
    roundtripped = list(_ps(srt_back))
    return original, roundtripped


def test_srt_roundtrip_ascii():
    original, roundtripped = _round_trip_segments(FIXTURES / "sample.srt")
    assert len(original) == len(roundtripped)
    for (o_start, _o_end, o_body), (r_start, _r_end, r_body) in zip(
        original, roundtripped
    ):
        assert abs(o_start - r_start) < 0.001
        assert o_body == r_body


def test_srt_roundtrip_unicode():
    original, roundtripped = _round_trip_segments(FIXTURES / "sample_unicode.srt")
    assert len(original) == len(roundtripped)
    for (o_start, _o_end, o_body), (r_start, _r_end, r_body) in zip(
        original, roundtripped
    ):
        assert abs(o_start - r_start) < 0.001
        assert o_body == r_body
    # The .otr text must keep non-ASCII Unicode characters verbatim.
    otr_string = srt_to_otr(str(FIXTURES / "sample_unicode.srt"), "audio.wav")
    assert "voilà" in json.loads(otr_string)["text"]


def test_whisper_json_to_otr():
    out = whisper_json_to_otr(str(FIXTURES / "sample_whisper.json"), "audio.wav")
    payload = json.loads(out)
    assert payload["text"].count('<span class="timestamp"') == 3
    # Round-trip back to SRT and confirm three segments.
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".otr", delete=False
    ) as tmp:
        tmp.write(out)
        otr_path = tmp.name
    try:
        srt_back = otr_to_srt(otr_path)
    finally:
        os.unlink(otr_path)
    from core.integrations.otranscribe import _parse_srt as _ps  # noqa: E402

    segments = list(_ps(srt_back))
    assert len(segments) == 3


def test_otr_text_uses_nbsp():
    out = srt_to_otr(str(FIXTURES / "sample.srt"), "audio.wav")
    text = json.loads(out)["text"]
    # NBSP (U+00A0) follows every closing </span>; a regular ASCII space must not.
    assert "</span> " in text
    assert "</span> " not in text  # regular ASCII space — would be a bug


def test_otr_text_single_line():
    out = srt_to_otr(str(FIXTURES / "sample.srt"), "audio.wav")
    text = json.loads(out)["text"]
    assert "\n" not in text
    assert "\r" not in text


def test_otr_to_srt_last_segment_end():
    payload = {
        "text": (
            '<p><span class="timestamp" contenteditable="false" '
            'data-timestamp="10.000">0:10</span> Only segment.</p>'
        ),
        "media": "x.mp3",
        "media-source": "",
        "media-time": 20.0,
    }
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".otr", delete=False
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False)
        otr_path = tmp.name
    try:
        srt = otr_to_srt(otr_path)
    finally:
        os.unlink(otr_path)
    from core.integrations.otranscribe import _parse_srt as _ps  # noqa: E402

    segs = list(_ps(srt))
    assert len(segs) == 1
    start, end, _body = segs[0]
    assert abs(start - 10.0) < 0.001
    assert abs(end - 20.0) < 1.0


def test_segments_to_otr_matches_writer_contract():
    """This is the entry point ``core.writers.otr`` calls, so its output
    must match the ``{start, end, text}`` writer contract used across
    ``core.writers`` / ``core.convert``, not the (start, end, body)
    tuples ``srt_to_otr``/``whisper_json_to_otr`` build internally."""
    segs = [
        {"start": 1.0, "end": 3.5, "text": "Hello world"},
        {"start": 3.5, "end": 6.0, "text": "Second line"},
    ]
    out = segments_to_otr(segs, media_filename="interview-01.mp3")
    payload = json.loads(out)
    assert set(payload.keys()) == {"text", "media", "media-source", "media-time"}
    assert payload["media"] == "interview-01.mp3"
    assert payload["text"].count('<span class="timestamp"') == 2
    assert "Hello world" in payload["text"]
    assert "Second line" in payload["text"]


def test_segments_to_otr_roundtrip():
    segs = [
        {"start": 1.0, "end": 3.5, "text": "Hello world"},
        {"start": 3.5, "end": 6.0, "text": "Second line"},
    ]
    otr_string = segments_to_otr(segs, "audio.wav")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".otr", delete=False
    ) as tmp:
        tmp.write(otr_string)
        otr_path = tmp.name
    try:
        srt_back = otr_to_srt(otr_path)
    finally:
        os.unlink(otr_path)
    from core.integrations.otranscribe import _parse_srt as _ps  # noqa: E402

    parsed = list(_ps(srt_back))
    assert len(parsed) == 2
    assert parsed[0][2] == "Hello world"
    assert parsed[1][2] == "Second line"


def test_media_field_basename_only():
    out = srt_to_otr(str(FIXTURES / "sample.srt"), "C:/path/to/audio.mp3")
    payload = json.loads(out)
    assert payload["media"] == "audio.mp3"
    out_unix = srt_to_otr(str(FIXTURES / "sample.srt"), "/var/data/file.wav")
    assert json.loads(out_unix)["media"] == "file.wav"
