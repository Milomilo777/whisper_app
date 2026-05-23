"""Tests for ``core._timecode`` — pure-function helpers."""
from __future__ import annotations

import random

import pytest

from core import _timecode as _tc


# ---------------------------------------------------------------- parse_timecode happy


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0", 0.0),
        ("1", 1.0),
        ("90", 90.0),
        ("7.25", 7.25),
        ("3600", 3600.0),
        ("0.001", 0.001),
        ("0:30", 30.0),
        ("1:30", 90.0),
        ("5:00", 300.0),
        ("10:00", 600.0),
        ("1:00:00", 3600.0),
        ("0:00:00", 0.0),
        ("0:00:51", 51.0),
        ("1:23:45", 5025.0),
        ("23:59:59", 86399.0),
        ("0:01:25.5", 85.5),
        ("0:00:00.001", 0.001),
    ],
)
def test_parse_timecode_happy(raw: str, expected: float) -> None:
    assert _tc.parse_timecode(raw) == pytest.approx(expected)


def test_parse_timecode_whitespace_tolerated() -> None:
    assert _tc.parse_timecode("   1:30   ") == 90.0


# ---------------------------------------------------------------- parse_timecode reject


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "   ",
        "abc",
        "1:2:3:4",          # too many parts
        "-1",                # negative seconds
        "-1:00",             # negative minutes
        "1:-5",              # negative inside
        "1:60",              # minute-seconds >= 60
        "1:90",
        "1:00:60",           # H:MM:SS >= 60
        "100000",            # > 24h
        "1:00:00.5xyz",
    ],
)
def test_parse_timecode_rejects(bad: str | None) -> None:
    assert _tc.parse_timecode(bad) is None


def test_parse_timecode_at_24h_boundary_accepted() -> None:
    """86400 = exactly 24h; the cap is inclusive on the value side."""
    assert _tc.parse_timecode("24:00:00") == 86400.0


def test_parse_timecode_past_24h_rejected() -> None:
    assert _tc.parse_timecode("25:00:00") is None


def test_parse_timecode_large_mm_ss_accepted() -> None:
    """MM:SS may exceed 60 minutes total; only sub-positions are
    capped at 60."""
    assert _tc.parse_timecode("999:00") == 999.0 * 60


def test_parse_timecode_just_under_cap() -> None:
    assert _tc.parse_timecode("23:59:59.999") == pytest.approx(86399.999, abs=1e-3)


# ---------------------------------------------------------------- fmt_timecode


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0.0, "0:00:00"),
        (1.0, "0:00:01"),
        (60.0, "0:01:00"),
        (3600.0, "1:00:00"),
        (3661.0, "1:01:01"),
        (90.5, "0:01:30.5"),
        (7322.25, "2:02:02.25"),
        (-5.0, "0:00:00"),
    ],
)
def test_fmt_timecode(seconds: float, expected: str) -> None:
    assert _tc.fmt_timecode(seconds) == expected


def test_fmt_timecode_negative_clamps_to_zero() -> None:
    assert _tc.fmt_timecode(-100.0) == "0:00:00"


def test_fmt_timecode_integer_no_decimal_suffix() -> None:
    out = _tc.fmt_timecode(7.0)
    assert "." not in out


def test_fmt_timecode_with_fraction_keeps_decimal() -> None:
    out = _tc.fmt_timecode(7.5)
    assert "." in out


# ---------------------------------------------------------------- download_sections_arg


def test_download_sections_arg_both_none() -> None:
    assert _tc.download_sections_arg(None, None) is None


def test_download_sections_arg_start_only() -> None:
    out = _tc.download_sections_arg(60.0, None)
    assert out == "*0:01:00-"


def test_download_sections_arg_end_only() -> None:
    out = _tc.download_sections_arg(None, 60.0)
    assert out == "*-0:01:00"


def test_download_sections_arg_both() -> None:
    out = _tc.download_sections_arg(30.0, 90.0)
    assert out == "*0:00:30-0:01:30"


def test_download_sections_arg_zero_zero() -> None:
    out = _tc.download_sections_arg(0.0, 0.0)
    assert out == "*0:00:00-0:00:00"


# ---------------------------------------------------------------- round-trip


@pytest.mark.parametrize(
    "raw",
    ["0:00:00", "0:01:30", "1:00:00", "0:00:01"],
)
def test_parse_then_fmt_round_trip(raw: str) -> None:
    secs = _tc.parse_timecode(raw)
    assert secs is not None
    back = _tc.fmt_timecode(secs)
    # We don't always get exactly the same string (e.g. leading zeros)
    # but parsing the formatted string should yield the same seconds.
    re_secs = _tc.parse_timecode(back)
    assert re_secs == pytest.approx(secs)


# ---------------------------------------------------------------- fuzz


def test_parse_timecode_fuzz_never_raises() -> None:
    """500 random short strings → parse_timecode must not raise."""
    rng = random.Random(42)
    chars = "0123456789:.- \t\nabcxyz"
    for _ in range(500):
        n = rng.randint(0, 12)
        s = "".join(rng.choice(chars) for _ in range(n))
        out = _tc.parse_timecode(s)
        assert out is None or isinstance(out, float)


def test_fmt_timecode_fuzz_never_raises() -> None:
    """200 random float values → fmt_timecode must not raise."""
    rng = random.Random(7)
    for _ in range(200):
        v = rng.uniform(-100, 100_000)
        out = _tc.fmt_timecode(v)
        assert isinstance(out, str)
