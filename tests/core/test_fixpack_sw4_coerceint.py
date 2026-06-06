"""Regression: _coerce_int must reject non-finite floats, not raise.

The LAN server's per-job integer options (``vad_min_silence_ms`` /
``diarization_num_speakers``) are coerced by ``_coerce_int`` on the
``POST /api/jobs`` path (``_options_from`` -> ``normalize_options``). It did
``int(_coerce_float(value))`` without rejecting non-finite floats: a client
sending an int option of ``'inf'`` / ``'nan'`` / ``'1e400'`` parses to
inf/nan, and ``int(inf)`` raises ``OverflowError`` while ``int(nan)`` raises
``ValueError``. Neither is caught in the POST handler, so the connection is
dropped (the client sees ``RemoteDisconnected``) instead of a clean 400.

The fix mirrors the ``float01`` clamp that already neutralises inf/nan:
``_coerce_int`` returns ``None`` for any non-finite value, and
``normalize_options`` already drops ``None`` options cleanly.

Hermetic pure-seam test: no socket, no network, no model, no Tk root.
On the pre-fix code the ``_coerce_int`` asserts raise OverflowError/ValueError
instead of returning None — so this test FAILS before the fix.
"""
from __future__ import annotations

from core.server.httpd import _coerce_int, normalize_options


# --- _coerce_int: non-finite inputs return None, never raise ----------------

def test_coerce_int_inf_string_returns_none():
    assert _coerce_int("inf") is None


def test_coerce_int_nan_string_returns_none():
    assert _coerce_int("nan") is None


def test_coerce_int_overflow_literal_returns_none():
    # '1e400' overflows a Python float to +inf.
    assert _coerce_int("1e400") is None


def test_coerce_int_signed_and_cased_non_finite_return_none():
    for raw in ("-inf", "Infinity", "-Infinity", "NaN", "  inf  "):
        assert _coerce_int(raw) is None


def test_coerce_int_non_finite_float_values_return_none():
    assert _coerce_int(float("inf")) is None
    assert _coerce_int(float("-inf")) is None
    assert _coerce_int(float("nan")) is None


# --- finite inputs still coerce as before -----------------------------------

def test_coerce_int_finite_still_works():
    assert _coerce_int("300") == 300
    assert _coerce_int("3.9") == 3
    assert _coerce_int(7) == 7
    assert _coerce_int(2.0) == 2
    assert _coerce_int("not a number") is None
    assert _coerce_int(None) is None


# --- end-to-end through normalize_options (the live POST path) --------------

def test_normalize_options_drops_non_finite_int_option():
    # Pre-fix this raised OverflowError inside normalize_options.
    out = normalize_options({"vad_min_silence_ms": "inf"})
    assert out == {}


def test_normalize_options_drops_nan_speakers_option():
    out = normalize_options({"diarization_num_speakers": "nan"})
    assert out == {}


def test_normalize_options_keeps_finite_alongside_dropped_non_finite():
    out = normalize_options({
        "vad_min_silence_ms": "1e400",   # dropped (overflow -> inf)
        "diarization_num_speakers": "2",  # kept
    })
    assert out == {"diarization_num_speakers": 2}
