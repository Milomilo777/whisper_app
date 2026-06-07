"""Regression: _safe_filename must not let a Windows RESERVED DEVICE name
through.

No socket, no model, no Tk. An upload named after a console/device alias
(CON, PRN, AUX, NUL, COM1-9, LPT1-9 — with or without an extension) used to
pass through ``_safe_filename`` unchanged. On Windows that path opens the
DEVICE, not a file: every byte written to ``NUL.wav`` is discarded, so the
job later dies with a misleading "no media file to transcribe" error. The
fix prefixes an underscore so the upload becomes an ordinary file.
"""
from __future__ import annotations

import os

from core.server.jobs import _safe_filename

# Inlined here (NOT imported from the module under test) so the test asserts
# the OBSERVABLE behaviour of _safe_filename and fails on the pre-fix code by
# behaviour, not by a missing-symbol import error.
_RESERVED = (
    frozenset({"CON", "PRN", "AUX", "NUL"})
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _is_reserved(name: str) -> bool:
    """True iff the extension-stripped stem is a reserved device name."""
    stem, _ext = os.path.splitext(name)
    return stem.upper() in _RESERVED


def test_reserved_name_with_extension_is_renamed():
    # 'NUL.wav' / 'com1.mp3' would otherwise route to the device.
    got = _safe_filename("NUL.wav")
    assert not _is_reserved(got)
    assert got == "_NUL.wav"

    got = _safe_filename("com1.mp3")
    assert not _is_reserved(got)
    assert got == "_com1.mp3"


def test_reserved_name_without_extension_is_renamed():
    got = _safe_filename("CON")
    assert not _is_reserved(got)
    assert got == "_CON"


def test_reserved_name_is_case_insensitive():
    # Mixed/upper/lower stem all map to the same device on Windows.
    for raw in ("con", "Con", "AuX", "lpt9.mkv", "PRN.txt"):
        got = _safe_filename(raw)
        assert not _is_reserved(got), f"{raw!r} -> {got!r} still reserved"


def test_reserved_guard_covers_every_device_name():
    for dev in _RESERVED:
        assert not _is_reserved(_safe_filename(dev))
        assert not _is_reserved(_safe_filename(dev + ".wav"))


def test_non_reserved_names_pass_through_unchanged():
    # The guard must not disturb ordinary filenames, including ones that
    # merely START with a reserved token but aren't an exact stem match.
    assert _safe_filename("clip.mp4") == "clip.mp4"
    assert _safe_filename("console.wav") == "console.wav"
    assert _safe_filename("connection.mp3") == "connection.mp3"
    assert _safe_filename("com10.wav") == "com10.wav"  # COM10 is not reserved
    assert _safe_filename("nul_take2.wav") == "nul_take2.wav"
