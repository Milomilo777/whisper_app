"""Backlog fixpack — writersstats cluster.

Regression for the only REAL candidate in this cluster:

``core.stats.count_words_in_segments`` and ``audio_duration_from_segments``
crashed with AttributeError on a list of NON-dict items (a hand-edited or
malformed JSON sidecar -> e.g. ``["a", "b"]`` or ``[1, 2, 3]``). The
duration helper's own ``except (TypeError, ValueError)`` does NOT catch
AttributeError, so the crash escaped. Both now skip / ignore non-dict
elements, matching their best-effort docstring contract.

These run against the existing-on-disk pre-fix code FAIL (AttributeError);
post-fix they pass. Hermetic: no Tk root, no network, no model.
"""
from __future__ import annotations

import pytest

from core import stats


# --- count_words_in_segments: non-dict elements ----------------------------

def test_count_words_in_segments_skips_non_dict_elements():
    """A list of plain strings must not AttributeError; non-dicts -> 0 words."""
    assert stats.count_words_in_segments(["a", "b"]) == 0  # type: ignore[list-item]


def test_count_words_in_segments_mixed_dict_and_non_dict():
    """Real segment dicts still count; non-dict items are skipped, not fatal."""
    segs = [
        {"text": "one two"},
        "garbage",           # non-dict -> skipped
        None,                # non-dict -> skipped
        123,                 # non-dict -> skipped
        {"text": "three"},
    ]
    assert stats.count_words_in_segments(segs) == 3  # type: ignore[list-item]


# --- audio_duration_from_segments: non-dict last element -------------------

def test_audio_duration_from_segments_non_dict_last_element():
    """A trailing non-dict element must clamp to 0.0, not AttributeError.

    AttributeError is not in the function's (TypeError, ValueError) handler,
    so without the isinstance guard this raised and escaped.
    """
    assert stats.audio_duration_from_segments(["a", "b"]) == 0.0  # type: ignore[list-item]
    assert stats.audio_duration_from_segments([1, 2, 3]) == 0.0  # type: ignore[list-item]


def test_audio_duration_from_segments_dict_last_still_works():
    """The normal dict path is unchanged by the guard."""
    segs = [{"start": 0.0, "end": 2.0}, {"start": 2.0, "end": 6.5}]
    assert stats.audio_duration_from_segments(segs) == pytest.approx(6.5)
