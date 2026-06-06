"""Regression test: a truncated cloud-STT chunk must NOT be returned silently.

Hermetic — NO network, NO API key, NO model, NO Tk. Exercises only the pure
``extract_text_from_response`` seam.

The defect: ``extract_text_from_response`` placed the ``finishReason != "STOP"``
guard INSIDE the ``if not text:`` branch. So when Gemini returned PARTIAL text
with ``finishReason == "MAX_TOKENS"`` (a dense ~8-min chunk exceeding the
output-token budget), the non-empty ``text`` branch was taken and the truncated
text was returned, silently dropping the rest of that chunk's audio from the
transcript -> data loss. The fix moves the guard so a non-STOP finishReason
aborts the chunk REGARDLESS of whether any partial text came back.

``test_extract_text_partial_text_max_tokens_raises`` below FAILS on the pre-fix
code (the function returns the partial string instead of raising).
"""
from __future__ import annotations

import pytest

from core.backends import cloud_stt as cs


def _candidate_response(text: str, finish_reason: str | None) -> dict:
    cand: dict = {"content": {"parts": [{"text": text}]}}
    if finish_reason is not None:
        cand["finishReason"] = finish_reason
    return {"candidates": [cand]}


def test_extract_text_partial_text_max_tokens_raises():
    """PARTIAL text + finishReason=MAX_TOKENS must raise, not return the stub.

    This is the data-loss case: the model produced *some* transcript but ran
    out of output tokens mid-chunk. Returning that partial string silently
    discards the rest of the chunk's audio.
    """
    resp = _candidate_response(
        "[00:00:01.000 --> 00:00:02.500] this clip got cut off mid-",
        "MAX_TOKENS",
    )
    with pytest.raises(RuntimeError) as e:
        cs.extract_text_from_response(resp)
    assert "MAX_TOKENS" in str(e.value)


def test_extract_text_partial_text_safety_raises():
    """SAFETY mid-stream is equally truncating and must also raise."""
    resp = _candidate_response("[00:00:00.000 --> 00:00:01.000] hello", "SAFETY")
    with pytest.raises(RuntimeError) as e:
        cs.extract_text_from_response(resp)
    assert "SAFETY" in str(e.value)


def test_extract_text_partial_text_recitation_raises():
    """RECITATION mid-stream is equally truncating and must also raise."""
    resp = _candidate_response("[00:00:00.000 --> 00:00:01.000] hello", "RECITATION")
    with pytest.raises(RuntimeError):
        cs.extract_text_from_response(resp)


def test_extract_text_clean_stop_with_text_still_returns():
    """A clean STOP with text is unaffected by the fix — returns the text."""
    resp = _candidate_response("[00:00:00.000 --> 00:00:01.000] hello", "STOP")
    assert cs.extract_text_from_response(resp).endswith("hello")


def test_extract_text_absent_finish_reason_with_text_returns():
    """No finishReason at all + text == safe; returns the text (not an abort)."""
    resp = _candidate_response("[00:00:00.000 --> 00:00:01.000] hello", None)
    assert cs.extract_text_from_response(resp).endswith("hello")


def test_extract_text_empty_clean_stop_returns_empty():
    """Empty text + clean STOP == genuine silence; returns '' (no raise)."""
    resp = _candidate_response("", "STOP")
    assert cs.extract_text_from_response(resp) == ""


def test_extract_text_empty_absent_reason_returns_empty():
    """Empty text + no finishReason == silence; returns '' (no raise)."""
    resp = _candidate_response("", None)
    assert cs.extract_text_from_response(resp) == ""
