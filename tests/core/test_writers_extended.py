"""Extensive writer coverage — SRT / JSON / TXT.

Parametrised to hit every meaningful edge case the writers might
encounter from a real transcribe pass: empty, unicode, very long,
malformed, negative timestamps, out-of-order segments, etc.
"""
from __future__ import annotations

import json
import math
from typing import Any

import pytest

from core.writers import get_writer, json_writer, srt, supported_formats, txt


# --------------------------------------------------------------------- helpers

def _segs(*pairs: tuple[float, float, str]) -> list[dict[str, Any]]:
    return [{"start": s, "end": e, "text": t} for s, e, t in pairs]


# --------------------------------------------------------------------- SRT


def test_srt_empty_list_produces_empty_string() -> None:
    assert srt.write([]) == ""


def test_srt_single_segment_basic_shape() -> None:
    out = srt.write(_segs((0.0, 1.0, "hi")))
    assert out.startswith("1\n00:00:00,000 --> 00:00:01,000\nhi\n")


@pytest.mark.parametrize(
    "text",
    [
        "",                             # empty
        "ascii only text",              # ASCII
        "café résumé naïve",            # latin-1
        "你好世界",                       # CJK
        "مرحبا بالعالم",                  # RTL
        "🎬 emoji 🎉",                  # emoji
        "tab\there\nnewline\rcr",        # control chars get collapsed
        "x" * 10_000,                    # very long
        "   trim me   ",                # whitespace
        "embedded --> arrow text",       # cue separator literal
    ],
)
def test_srt_single_segment_text_variations(text: str) -> None:
    out = srt.write(_segs((0.0, 1.0, text)))
    # Always 4 lines (index, timecode, text, blank).
    parts = out.split("\n")
    assert parts[0] == "1"
    assert " --> " in parts[1]
    # Cue separator must be escaped to unicode arrow.
    assert "-->" not in parts[2] or parts[2].count("-->") == 0


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0.0, "00:00:00,000"),
        (0.001, "00:00:00,001"),
        (0.999, "00:00:00,999"),
        (1.0, "00:00:01,000"),
        (1.5, "00:00:01,500"),
        (59.999, "00:00:59,999"),
        (60.0, "00:01:00,000"),
        (3599.999, "00:59:59,999"),
        (3600.0, "01:00:00,000"),
        (86399.999, "23:59:59,999"),
        (86400.0, "24:00:00,000"),
        (3723.456, "01:02:03,456"),
    ],
)
def test_fmt_srt_time_boundaries(seconds: float, expected: str) -> None:
    assert srt._fmt_srt_time(seconds) == expected


@pytest.mark.parametrize(
    "bad",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        -1.0,
        -100.5,
        -0.001,
    ],
)
def test_fmt_srt_time_clamps_invalid_to_zero(bad: float) -> None:
    assert srt._fmt_srt_time(bad) == "00:00:00,000"


@pytest.mark.parametrize("bad", [None, "abc", [], {}, object()])
def test_fmt_srt_time_handles_non_numeric(bad: object) -> None:
    out = srt._fmt_srt_time(bad)  # type: ignore[arg-type]
    assert out == "00:00:00,000"


def test_srt_negative_start_clamps_to_zero() -> None:
    out = srt.write(_segs((-5.0, 2.0, "x")))
    assert "00:00:00,000 --> 00:00:02,000" in out


def test_srt_zero_length_segment() -> None:
    out = srt.write(_segs((1.0, 1.0, "instant")))
    assert "00:00:01,000 --> 00:00:01,000" in out


def test_srt_end_before_start_does_not_crash() -> None:
    # Writer doesn't clamp end<start — it just renders what it gets.
    out = srt.write(_segs((5.0, 2.0, "weird")))
    assert "00:00:05,000 --> 00:00:02,000" in out


def test_srt_handles_int_timestamps() -> None:
    """``start``/``end`` may arrive as ints; float() conversion is applied."""
    out = srt.write([{"start": 0, "end": 1, "text": "x"}])
    assert "00:00:00,000 --> 00:00:01,000" in out


def test_srt_handles_missing_text_key() -> None:
    out = srt.write([{"start": 0.0, "end": 1.0}])
    # Default empty text → empty line.
    assert "00:00:00,000 --> 00:00:01,000\n\n" in out


def test_srt_collapses_internal_whitespace() -> None:
    out = srt.write(_segs((0.0, 1.0, "   too   much    space   ")))
    assert "too much space\n" in out


def test_srt_escapes_arrow_in_text() -> None:
    out = srt.write(_segs((0.0, 1.0, "before --> after")))
    assert "before → after" in out
    # And it should still appear only at the timecode separator position.
    timecode_lines = [ln for ln in out.split("\n") if " --> " in ln]
    assert len(timecode_lines) == 1


def test_srt_indices_are_sequential() -> None:
    out = srt.write([
        {"start": float(i), "end": float(i + 1), "text": f"line{i}"}
        for i in range(50)
    ])
    lines = out.split("\n")
    # Every block-of-4 starts with the next index.
    assert lines[0] == "1"
    assert lines[4] == "2"
    assert lines[8] == "3"


def test_srt_preserves_segment_order_as_given() -> None:
    """Out-of-order input → writer renders the order it was given."""
    out = srt.write([
        {"start": 5.0, "end": 6.0, "text": "third"},
        {"start": 1.0, "end": 2.0, "text": "first"},
        {"start": 3.0, "end": 4.0, "text": "second"},
    ])
    third_pos = out.index("third")
    first_pos = out.index("first")
    second_pos = out.index("second")
    assert third_pos < first_pos < second_pos


def test_srt_1000_segments_sanity() -> None:
    segs = [
        {"start": float(i), "end": float(i + 1), "text": f"seg{i}"}
        for i in range(1000)
    ]
    out = srt.write(segs)
    assert "\n1000\n" in out
    assert out.count(" --> ") == 1000


def test_srt_normalize_text_empty_str() -> None:
    assert srt._normalize_text("") == ""


def test_srt_normalize_text_none() -> None:
    assert srt._normalize_text(None) == ""  # type: ignore[arg-type]


def test_srt_escape_cue_separator_empty() -> None:
    assert srt._escape_cue_separator("") == ""


def test_srt_escape_cue_separator_no_arrow() -> None:
    assert srt._escape_cue_separator("normal text") == "normal text"


def test_srt_escape_cue_separator_multiple() -> None:
    out = srt._escape_cue_separator("a --> b --> c")
    assert "-->" not in out
    assert out.count("→") == 2


# --------------------------------------------------------------------- JSON


def test_json_empty_list_yields_empty_array() -> None:
    body = json_writer.write([])
    parsed = json.loads(body)
    assert parsed == []


@pytest.mark.parametrize(
    "text",
    [
        "",                       # empty
        "ascii",
        "café",                   # latin-1
        "你好",                    # CJK
        "🎬",                     # emoji
        "مرحبا",                  # RTL
        "x" * 10_000,
        "tab\there",
        "with \"quotes\"",        # JSON-tricky chars
        "with\nnewline",
        "with\\backslash",
        "/forward/slash",
    ],
)
def test_json_text_variations_round_trip(text: str) -> None:
    body = json_writer.write(_segs((0.0, 1.0, text)))
    data = json.loads(body)
    assert data[0]["text"] == text.strip()


@pytest.mark.parametrize(
    "start, end",
    [
        (0.0, 1.0),
        (0.0, 0.0),
        (1.5, 3.25),
        (60.0, 120.0),
        (3600.0, 7200.0),
        (86400.0, 86401.0),
    ],
)
def test_json_timestamp_round_trips(start: float, end: float) -> None:
    body = json_writer.write(_segs((start, end, "x")))
    data = json.loads(body)
    assert data[0]["start"] == start
    assert data[0]["end"] == end


@pytest.mark.parametrize(
    "bad",
    [float("nan"), float("inf"), float("-inf")],
)
def test_json_non_finite_replaced_with_zero(bad: float) -> None:
    body = json_writer.write([{"start": bad, "end": bad, "text": "x"}])
    data = json.loads(body)
    assert data[0]["start"] == 0.0
    assert data[0]["end"] == 0.0


def test_json_strict_no_nan() -> None:
    """allow_nan=False on output → strict parsers can consume it."""
    body = json_writer.write([{"start": float("nan"), "end": float("inf"), "text": "x"}])
    # Should NOT contain NaN/Infinity in the raw bytes.
    assert "NaN" not in body
    assert "Infinity" not in body


@pytest.mark.parametrize(
    "bad_text",
    [None, [], {}],  # falsy non-strings → ("" or default) short-circuit works
)
def test_json_falsy_non_string_text_handled(bad_text: object) -> None:
    body = json_writer.write([{"start": 0.0, "end": 1.0, "text": bad_text}])
    data = json.loads(body)
    assert "text" in data[0]


@pytest.mark.parametrize("bad_text", [42, 3.14, True, [1], {"k": 1}])
def test_json_truthy_non_string_text_coerced(bad_text: object) -> None:
    """Regression: int / float / True / list / dict text values used to
    crash ``json_writer.write`` with ``AttributeError`` because
    ``(seg.get("text") or "").strip()`` short-circuits on falsy values
    only — truthy non-strings would hit ``.strip()``. The fix coerces
    via ``str(...)`` first."""
    body = json_writer.write([{"start": 0.0, "end": 1.0, "text": bad_text}])
    data = json.loads(body)
    assert "text" in data[0]
    assert isinstance(data[0]["text"], str)


def test_json_missing_start_defaults_zero() -> None:
    body = json_writer.write([{"end": 1.0, "text": "x"}])
    data = json.loads(body)
    assert data[0]["start"] == 0.0


def test_json_missing_end_defaults_zero() -> None:
    body = json_writer.write([{"start": 1.0, "text": "x"}])
    data = json.loads(body)
    assert data[0]["end"] == 0.0


def test_json_empty_segment_dict() -> None:
    body = json_writer.write([{}])
    data = json.loads(body)
    assert data[0]["start"] == 0.0 and data[0]["end"] == 0.0 and data[0]["text"] == ""


def test_json_indented_output() -> None:
    body = json_writer.write(_segs((0.0, 1.0, "x")))
    # indent=2 means lines have leading spaces inside the array.
    assert "  {" in body


def test_json_unicode_not_escaped() -> None:
    body = json_writer.write(_segs((0.0, 1.0, "你好")))
    # ensure_ascii=False keeps unicode literal.
    assert "你好" in body


def test_json_trailing_newline() -> None:
    body = json_writer.write(_segs((0.0, 1.0, "x")))
    assert body.endswith("\n")


def test_json_text_stripped() -> None:
    body = json_writer.write(_segs((0.0, 1.0, "  padded  ")))
    data = json.loads(body)
    assert data[0]["text"] == "padded"


def test_json_safe_float_handles_strings() -> None:
    assert json_writer._safe_float("1.5") == 1.5
    assert json_writer._safe_float("nan", default=42.0) == 42.0
    assert json_writer._safe_float("not-a-number", default=0.0) == 0.0


@pytest.mark.parametrize("bad", [None, [], {}, object()])
def test_json_safe_float_non_numeric(bad: object) -> None:
    assert json_writer._safe_float(bad) == 0.0


def test_json_1000_segments_round_trip() -> None:
    segs = [
        {"start": float(i), "end": float(i + 1), "text": f"seg{i}"}
        for i in range(1000)
    ]
    body = json_writer.write(segs)
    data = json.loads(body)
    assert len(data) == 1000
    assert data[999]["text"] == "seg999"


def test_json_preserves_order() -> None:
    body = json_writer.write([
        {"start": 5.0, "end": 6.0, "text": "third"},
        {"start": 1.0, "end": 2.0, "text": "first"},
    ])
    data = json.loads(body)
    assert data[0]["text"] == "third"
    assert data[1]["text"] == "first"


def test_json_negative_timestamps_pass_through() -> None:
    body = json_writer.write([{"start": -5.0, "end": 1.0, "text": "x"}])
    data = json.loads(body)
    # _safe_float doesn't clamp negatives — only NaN/Inf.
    assert data[0]["start"] == -5.0


# --------------------------------------------------------------------- TXT


def test_txt_empty_list_yields_one_newline() -> None:
    # write returns "\n".join([]) + "\n" = "\n"
    assert txt.write([]) == "\n"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", ""),
        ("hello world", "hello world"),
        ("café résumé", "café résumé"),
        ("你好世界", "你好世界"),
        ("مرحبا", "مرحبا"),
        ("🎬 emoji 🎉", "🎬 emoji 🎉"),
        ("   leading and trailing   ", "leading and trailing"),
        ("multiple   spaces   here", "multiple spaces here"),
        ("tab\there", "tab here"),
        ("new\nline", "new line"),
        ("cr\rhere", "cr here"),
        ("mixed\n\n\twhitespace", "mixed whitespace"),
    ],
)
def test_txt_normalizes_text(text: str, expected: str) -> None:
    out = txt.write(_segs((0.0, 1.0, text)))
    assert out == expected + "\n"


def test_txt_one_segment_per_line() -> None:
    out = txt.write(_segs(
        (0.0, 1.0, "first"),
        (1.0, 2.0, "second"),
        (2.0, 3.0, "third"),
    ))
    assert out == "first\nsecond\nthird\n"


def test_txt_no_extra_blank_lines() -> None:
    out = txt.write(_segs(
        (0.0, 1.0, "a"),
        (1.0, 2.0, "b"),
    ))
    # exactly 2 \n, one between + one trailing.
    assert out.count("\n") == 2


def test_txt_handles_missing_text_key() -> None:
    out = txt.write([{"start": 0.0, "end": 1.0}])
    assert out == "\n"


def test_txt_handles_none_text() -> None:
    out = txt.write([{"start": 0.0, "end": 1.0, "text": None}])
    assert out == "\n"


def test_txt_very_long_text() -> None:
    long_text = "x" * 10_000
    out = txt.write(_segs((0.0, 1.0, long_text)))
    assert out == long_text + "\n"


def test_txt_1000_segments_one_per_line() -> None:
    segs = [
        {"start": float(i), "end": float(i + 1), "text": f"line-{i}"}
        for i in range(1000)
    ]
    out = txt.write(segs)
    lines = out.rstrip("\n").split("\n")
    assert len(lines) == 1000
    assert lines[0] == "line-0"
    assert lines[999] == "line-999"


def test_txt_normalize_returns_str_for_none() -> None:
    assert txt._normalize(None) == ""  # type: ignore[arg-type]


def test_txt_unicode_not_escaped() -> None:
    out = txt.write(_segs((0.0, 1.0, "你好")))
    assert "你好" in out


def test_txt_does_not_emit_timestamps() -> None:
    out = txt.write(_segs((0.0, 1.0, "no timestamps")))
    assert "00:00" not in out
    assert "-->" not in out


# --------------------------------------------------------------------- writers __init__


def test_supported_formats_sorted_alphabetically() -> None:
    formats = supported_formats()
    assert formats == sorted(formats)


@pytest.mark.parametrize("name", ["srt", "json", "txt"])
def test_get_writer_returns_callable(name: str) -> None:
    fn = get_writer(name)
    assert callable(fn)


@pytest.mark.parametrize("name", ["SRT", "Json", "TXT", "sRT"])
def test_get_writer_case_insensitive(name: str) -> None:
    fn = get_writer(name)
    assert callable(fn)


@pytest.mark.parametrize("bad", ["docx", "vtt", "ttml", "", "  "])
def test_get_writer_raises_keyerror_on_unknown(bad: str) -> None:
    with pytest.raises(KeyError):
        get_writer(bad)


def test_supported_formats_returns_list() -> None:
    assert isinstance(supported_formats(), list)


def test_supported_formats_no_duplicates() -> None:
    formats = supported_formats()
    assert len(formats) == len(set(formats))


# --------------------------------------------------------------------- filename safety
# Writers don't write files themselves; they return strings. So
# "filename with spaces" tests against the transcriber's _write_outputs
# instead. Here we just verify the writer body doesn't carry the
# filename.


def test_writers_ignore_audio_path() -> None:
    # All three writers accept audio_path but should not embed it.
    body_srt = srt.write(_segs((0.0, 1.0, "x")), "/some/path/with spaces.mp3")
    body_json = json_writer.write(_segs((0.0, 1.0, "x")), "/some/path/with spaces.mp3")
    body_txt = txt.write(_segs((0.0, 1.0, "x")), "/some/path/with spaces.mp3")
    assert "with spaces" not in body_srt
    assert "with spaces" not in body_json
    assert "with spaces" not in body_txt


@pytest.mark.parametrize(
    "weird_audio_path",
    [
        "/path/with spaces/audio.mp3",
        "/path/with(parens)/audio.mp3",
        "/path/with'quotes'/audio.mp3",
        "/path/with视频/audio.mp3",
        "/path/with🎬emoji/audio.mp3",
        "",
        " ",
    ],
)
def test_writers_accept_weird_audio_paths(weird_audio_path: str) -> None:
    """Writers must not crash on weird audio_path values."""
    srt.write(_segs((0.0, 1.0, "x")), weird_audio_path)
    json_writer.write(_segs((0.0, 1.0, "x")), weird_audio_path)
    txt.write(_segs((0.0, 1.0, "x")), weird_audio_path)


# --------------------------------------------------------------------- structural


@pytest.mark.parametrize("n", [0, 1, 5, 50, 200])
def test_srt_block_count(n: int) -> None:
    segs = [{"start": float(i), "end": float(i + 1), "text": f"s{i}"} for i in range(n)]
    out = srt.write(segs)
    # SRT cues are numbered blocks ending in blank line.
    if n == 0:
        assert out == ""
    else:
        # Every cue → 4 lines + 1 trailing newline at end.
        # split on "\n" gives at least n*4 entries.
        timecodes = [ln for ln in out.split("\n") if " --> " in ln]
        assert len(timecodes) == n


@pytest.mark.parametrize("n", [0, 1, 5, 50, 200])
def test_json_array_count(n: int) -> None:
    segs = [{"start": float(i), "end": float(i + 1), "text": f"s{i}"} for i in range(n)]
    body = json_writer.write(segs)
    parsed = json.loads(body)
    assert len(parsed) == n


@pytest.mark.parametrize("n", [0, 1, 5, 50, 200])
def test_txt_line_count(n: int) -> None:
    segs = [{"start": float(i), "end": float(i + 1), "text": f"s{i}"} for i in range(n)]
    out = txt.write(segs)
    lines = out.rstrip("\n").split("\n")
    # An empty input produces [""] from "\n".rstrip("\n").split("\n").
    if n == 0:
        assert lines == [""]
    else:
        assert len(lines) == n
