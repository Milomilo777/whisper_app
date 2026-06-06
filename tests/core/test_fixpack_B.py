"""Fixpack B regression tests for ``core.convert``.

Covers two confirmed bugs:

1. Windows case-insensitive overwrite guard: a default output path that
   differs from the input ONLY in extension case (``Movie.SRT`` ->
   ``Movie.srt``) names the SAME file on a case-insensitive filesystem.
   The old ``os.path.abspath`` string compare missed that and overwrote
   the source in place; the fix compares ``normcase(realpath(...))`` and
   applies the ``.converted`` suffix.

2. Non-dict ``words`` entries in input JSON: ``_parse_json`` used to carry
   the whole ``words`` list through unchecked, so a bare string / number
   element made the downstream JSON and VTT writers' ``w.get(...)`` raise
   AttributeError and abort the whole conversion. The fix filters ``words``
   to dict elements only.
"""
from __future__ import annotations

import json
import os

import pytest

from core import convert


# --- Bug 1: case-only path difference must not clobber the source -----------

def test_same_file_detects_case_only_difference(tmp_path):
    """_same_file treats a case-only extension difference as the same file
    on a case-insensitive FS (Windows), and as distinct on a case-sensitive
    FS (Linux) — matching the real filesystem semantics either way."""
    upper = tmp_path / "Movie.SRT"
    upper.write_text("x", encoding="utf-8")
    lower_name = str(tmp_path / "Movie.srt")

    case_insensitive = os.path.exists(lower_name)
    # _same_file must agree with what the OS actually reports.
    assert convert._same_file(str(upper), lower_name) is case_insensitive


def test_convert_case_only_extension_does_not_clobber_source(tmp_path):
    """On a case-insensitive FS, converting Movie.SRT -> srt must NOT write
    over the source; it must fall back to the .converted suffix."""
    src = tmp_path / "Movie.SRT"
    body = (
        "1\n"
        "00:00:01,000 --> 00:00:03,500\n"
        "Hello world\n"
    )
    src.write_text(body, encoding="utf-8")

    # Only meaningful where the FS is case-insensitive (the default-out path
    # 'Movie.srt' resolves to the same file as 'Movie.SRT').
    default_out = str(tmp_path / "Movie.srt")
    if not os.path.exists(default_out):
        pytest.skip("case-sensitive filesystem: no case-only collision")

    out = convert.convert_file(str(src), "srt")
    # Guard must fire: output goes to the .converted variant, not the source.
    assert ".converted" in out
    assert not convert._same_file(out, str(src))
    # The original transcript is untouched.
    assert src.read_text(encoding="utf-8") == body


def test_convert_explicit_out_path_case_only_difference(tmp_path):
    """A caller-supplied out_path that differs from the input only in case
    is also guarded (same realpath/normcase compare)."""
    src = tmp_path / "Clip.VTT"
    src.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi\n", encoding="utf-8"
    )
    explicit = str(tmp_path / "Clip.vtt")  # same file, different case
    if not convert._same_file(str(src), explicit):
        pytest.skip("case-sensitive filesystem: paths are genuinely distinct")

    out = convert.convert_file(str(src), "vtt", explicit)
    assert ".converted" in out
    assert not convert._same_file(out, str(src))


def test_convert_distinct_path_is_left_alone(tmp_path):
    """A genuinely different target keeps its name — the guard is scoped to
    the overwrite case only."""
    src = tmp_path / "a.json"
    src.write_text(
        json.dumps([{"start": 0.0, "end": 1.0, "text": "hi"}]),
        encoding="utf-8",
    )
    target = str(tmp_path / "b.srt")
    out = convert.convert_file(str(src), "srt", target)
    assert out == target
    assert ".converted" not in out


# --- Bug 2: non-dict elements in a JSON 'words' list ------------------------

_BAD_WORDS_JSON = json.dumps(
    [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "hello",
            "words": ["hel", "lo", 42, None],  # all non-dict
        }
    ]
)

_MIXED_WORDS_JSON = json.dumps(
    [
        {
            "start": 0.0,
            "end": 2.0,
            "text": "hello world",
            "words": [
                "junk",
                {"start": 0.0, "end": 1.0, "word": "hello", "probability": 0.9},
                123,
                {"start": 1.0, "end": 2.0, "word": "world", "probability": 0.8},
            ],
        }
    ]
)


def test_parse_json_drops_non_dict_words():
    segs = convert._parse_json(_BAD_WORDS_JSON, "bad.json")
    assert len(segs) == 1
    # No usable word dicts -> 'words' is omitted entirely (not a list of junk).
    assert "words" not in segs[0]


def test_parse_json_keeps_only_dict_words():
    segs = convert._parse_json(_MIXED_WORDS_JSON, "mixed.json")
    assert len(segs) == 1
    words = segs[0]["words"]
    assert all(isinstance(w, dict) for w in words)
    assert [w["word"] for w in words] == ["hello", "world"]


@pytest.mark.parametrize("out_fmt", ["vtt", "json", "srt"])
def test_convert_bad_words_json_does_not_crash(tmp_path, out_fmt):
    """End to end: a JSON input with a bad 'words' list converts cleanly to
    every text format instead of raising AttributeError."""
    p = tmp_path / "in.json"
    p.write_text(_BAD_WORDS_JSON, encoding="utf-8")
    out = convert.convert_file(str(p), out_fmt)
    text = open(out, encoding="utf-8").read()
    assert "hello" in text


@pytest.mark.parametrize("out_fmt", ["vtt", "json"])
def test_convert_mixed_words_json_keeps_valid_words(tmp_path, out_fmt):
    p = tmp_path / "mixed.json"
    p.write_text(_MIXED_WORDS_JSON, encoding="utf-8")
    out = convert.convert_file(str(p), out_fmt)
    text = open(out, encoding="utf-8").read()
    assert "hello" in text
    assert "world" in text
