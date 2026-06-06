"""Regression: live VLC karaoke highlighting must not crash when a
loaded segment carries a NON-NUMERIC ``start`` / ``end`` value.

``_update_karaoke`` runs on every ~250-ms playhead tick. It read each
segment's ``start`` (to build the bisect list) and the candidate
segment's ``start`` / ``end`` with a bare ``float(seg.get(...))``. A
single hand-edited / locale-formatted transcript whose ``start`` is a
European decimal string (``"1,5"``) or a stray ``"abc"`` made that
``float()`` raise ``ValueError`` mid-tick — and because the exception
propagated out of the tick callback, it broke ALL subsequent karaoke
highlighting for the whole playback session. The defensive
``_seg_float`` helper (added for exactly this malformed input) was used
elsewhere in the viewer but NOT on these three reads.

This test exercises the pure highlight seam without a Tk root, a media
file, VLC, or a network: ``_update_karaoke`` driven against an instance
built with ``TranscriptViewer.__new__`` plus stubbed attributes (the
words label + the active-segment setter). On the pre-fix code it raises
``ValueError`` and fails.
"""
from __future__ import annotations

import pytest


class _StubLabel:
    """Minimal stand-in for the ttk.Label the karaoke path configures."""

    def __init__(self) -> None:
        self.text = ""

    def configure(self, *, text: str = "") -> None:
        self.text = text


def _make_viewer(segments):
    """Build a TranscriptViewer instance WITHOUT running __init__ (no Tk
    root / no VLC), wired with just the attributes ``_update_karaoke``
    reads. This is the pure highlight seam for an app/dialogs Tk class."""
    from app.dialogs.transcript_viewer import TranscriptViewer

    v = TranscriptViewer.__new__(TranscriptViewer)
    v.segments = segments  # type: ignore[attr-defined]
    v._active_segment_idx = None  # type: ignore[attr-defined]
    v._active_word_idx = None  # type: ignore[attr-defined]
    v._words_lbl = _StubLabel()  # type: ignore[attr-defined]

    # Stub the active-segment setter so we don't drag in the Treeview /
    # tag machinery; just record the index the tick would activate.
    def _set_active_segment(idx):
        v._active_segment_idx = idx  # type: ignore[attr-defined]
        v._active_word_idx = None  # type: ignore[attr-defined]

    v._set_active_segment = _set_active_segment  # type: ignore[attr-defined]
    return v


def test_update_karaoke_survives_non_numeric_start_end():
    """A segment whose start/end are non-numeric must not raise during a
    playhead tick; the offending timestamps coerce to 0.0 rather than
    breaking all live highlighting."""
    from app.dialogs.transcript_viewer import TranscriptViewer

    segments = [
        {"start": "1,5", "end": "3,0", "text": "european decimal"},
        {"start": "abc", "end": "xyz", "text": "pure garbage"},
        {"start": None, "end": None, "text": "null timestamps"},
        {"start": 4.0, "end": 5.0, "text": "legit numeric"},
    ]
    viewer = _make_viewer(segments)

    # On the pre-fix code this raises ValueError: could not convert
    # string to float: '1,5'.
    TranscriptViewer._update_karaoke(viewer, 0.0)
    TranscriptViewer._update_karaoke(viewer, 2.0)


def test_update_karaoke_highlights_legit_segment_after_bad_one():
    """A malformed segment earlier in the list must not stop a later,
    well-formed segment from being highlighted at its playhead time."""
    from app.dialogs.transcript_viewer import TranscriptViewer

    segments = [
        {"start": "abc", "end": "xyz", "text": "garbage"},
        {"start": 4.0, "end": 5.0, "text": "legit numeric"},
    ]
    viewer = _make_viewer(segments)

    TranscriptViewer._update_karaoke(viewer, 4.5)

    # The well-formed segment at index 1 must be the active one.
    assert viewer._active_segment_idx == 1  # type: ignore[attr-defined]
    assert viewer._words_lbl.text == "legit numeric"  # type: ignore[attr-defined]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
