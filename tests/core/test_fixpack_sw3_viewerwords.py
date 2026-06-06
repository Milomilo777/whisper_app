"""Regression: the transcript viewer must not crash when a loaded
segment's ``words`` is a list of NON-dict elements.

A normal Whisper transcript carries ``words`` as a list of dicts
(``{"word": ..., "start": ..., "end": ..., "probability": ...}``). But
a hand-edited or unrelated JSON may carry a list of NON-dict elements
(e.g. ``words: [1, 2]`` or ``["a"]``). ``_segment_min_probability``
iterated that list and called ``w.get("probability", ...)`` on each
element; on a non-dict that raises ``AttributeError`` — which the
``(TypeError, ValueError)`` handler does NOT catch — crashing the viewer
during construction (``_populate_listbox`` calls the helper for every
row) and bypassing the friendly "pick the .json" guard in
``_load_segments``.

These tests exercise the pure helper seam without a Tk root, a media
file, VLC, or a network. On the pre-fix code the non-dict cases raise
``AttributeError`` and fail.
"""
from __future__ import annotations


def test_segment_min_probability_skips_non_dict_words():
    from app.dialogs.transcript_viewer import _segment_min_probability

    # List of ints — the canonical crash case (w.get on an int).
    assert _segment_min_probability({"words": [1, 2]}) is None
    # List of strings.
    assert _segment_min_probability({"words": ["a", "b"]}) is None
    # Mixed: a couple of garbage entries plus one real word dict. The
    # non-dicts are skipped; the real probability still drives the result.
    seg_mixed = {"words": [1, "x", {"probability": 0.42}, None]}
    assert _segment_min_probability(seg_mixed) == 0.42
    # None / non-list ``words`` still collapses cleanly to None.
    assert _segment_min_probability({"words": None}) is None
    assert _segment_min_probability({}) is None


def test_segment_min_probability_still_handles_real_dicts():
    """The fix must not regress the normal list-of-dicts path."""
    from app.dialogs.transcript_viewer import _segment_min_probability

    seg = {"words": [{"probability": 0.9}, {"probability": 0.7}, {"probability": 0.95}]}
    assert _segment_min_probability(seg) == 0.7
    # Empty word list → no probabilities available.
    assert _segment_min_probability({"words": []}) is None
    # A dict word with a non-numeric probability is coerced/skipped by the
    # existing (TypeError, ValueError) guard, not the new isinstance one.
    assert _segment_min_probability({"words": [{"probability": "abc"}]}) is None
