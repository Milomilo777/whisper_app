"""Hermetic regression test for the cloud-STT multi-chunk empty-window fix.

Defect (pre-fix): in the multi-chunk Gemini loop of
``CloudSttBackend.transcribe_to_segments``, a chunk that contains no
recognizable speech (music / applause / silence / a per-clip safety pass)
came back as a candidate that finished cleanly (``finishReason == "STOP"``)
but with empty text. ``extract_text_from_response`` raised
``RuntimeError("...empty transcript...")`` for that case, and the per-chunk
``try/finally`` does NOT catch it — so the WHOLE job aborted and every
segment collected from earlier successful chunks was discarded. The sibling
``google_cloud_stt`` backend tolerates an empty window (0 segments) and
continues.

Fix: a candidate that stopped cleanly but is empty now yields ``""`` (-> 0
segments) instead of raising, so one silent chunk no longer destroys the
rest of a multi-chunk transcription. Genuine failures — an ``error``
payload, a whole-prompt ``blockReason``, or a bad ``finishReason``
(``SAFETY`` / ``MAX_TOKENS``) — still raise.

NO network, NO API key, NO model, NO ffmpeg, NO Tk. The FLAC encoder and
``urllib.request.urlopen`` are stubbed.
"""
from __future__ import annotations

import io
import json
from typing import Any

import pytest

from core.backends import cloud_stt as cs


# ---------------------------------------------------------------- fakes


class _FakeResp:
    """Minimal context-manager stand-in for an http.client response."""

    def __init__(self, body: bytes = b"", headers: dict[str, str] | None = None):
        self._buf = io.BytesIO(body)
        self.headers = headers or {}

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self, n: int = -1) -> bytes:
        return self._buf.read() if n == -1 else self._buf.read(n)


def _speech_response(text: str) -> bytes:
    return json.dumps(
        {"candidates": [{"content": {"parts": [{"text": text}]},
                         "finishReason": "STOP"}]}
    ).encode("utf-8")


def _empty_stop_response() -> bytes:
    """A candidate that stopped cleanly but produced no transcript text —
    what Gemini returns for a music / silence / applause-only window."""
    return json.dumps(
        {"candidates": [{"content": {"parts": [{"text": ""}]},
                         "finishReason": "STOP"}]}
    ).encode("utf-8")


def _backend() -> cs.CloudSttBackend:
    b = cs.CloudSttBackend(
        config={"cloud_stt_api_key": "SECRET-KEY-123", "cloud_stt_model": "m"}
    )
    assert b.load() is True
    return b


# ---------------------------------------------------------------- unit seam


def test_empty_but_clean_stop_returns_empty_string_not_raise():
    """A clean-STOP candidate with no text is a silent window, not an error:
    it must yield "" (PRE-FIX this raised, aborting the run)."""
    resp = {
        "candidates": [
            {"content": {"parts": [{"text": ""}]}, "finishReason": "STOP"}
        ]
    }
    assert cs.extract_text_from_response(resp) == ""
    # "" -> zero segments, so the chunk simply contributes nothing.
    assert cs.parse_transcript_to_segments(
        cs.extract_text_from_response(resp)
    ) == []


def test_empty_with_no_finish_reason_returns_empty_string():
    """A candidate with neither text nor a finishReason is also treated as a
    benign empty window."""
    resp = {"candidates": [{"content": {"parts": [{"text": ""}]}}]}
    assert cs.extract_text_from_response(resp) == ""


def test_genuine_failures_still_raise():
    """The fix must NOT swallow real failures."""
    # Bad finishReason (output truncated).
    with pytest.raises(RuntimeError):
        cs.extract_text_from_response(
            {"candidates": [{"content": {"parts": [{"text": ""}]},
                             "finishReason": "MAX_TOKENS"}]}
        )
    # Per-clip safety stop.
    with pytest.raises(RuntimeError):
        cs.extract_text_from_response(
            {"candidates": [{"content": {"parts": [{"text": ""}]},
                             "finishReason": "SAFETY"}]}
        )
    # Whole-prompt block.
    with pytest.raises(RuntimeError):
        cs.extract_text_from_response({"promptFeedback": {"blockReason": "SAFETY"}})
    # API error object.
    with pytest.raises(RuntimeError):
        cs.extract_text_from_response({"error": {"message": "boom"}})


# ---------------------------------------------------------------- integration


def test_empty_second_chunk_keeps_first_chunk_segments(monkeypatch, tmp_path):
    """End-to-end seam: a 2-chunk run where chunk 1 has speech and chunk 2 is
    an empty (music/silence) window must STILL return chunk 1's segments
    rather than raising and discarding them.

    PRE-FIX: the empty chunk made ``extract_text_from_response`` raise an
    uncaught RuntimeError inside the per-chunk try/finally, aborting the whole
    ``transcribe_to_segments`` call -> this test raised instead of returning.
    """
    # Stub the ffmpeg encoder: each call writes a fresh tiny real file
    # (small -> the inline path, so the only network calls are the two
    # generateContent POSTs). A fresh file per chunk also survives the
    # per-chunk ``os.unlink`` cleanup in the loop's finally.
    flac = tmp_path / "chunk.flac"

    def fake_encode(audio_path, start, end):  # noqa: ANN001
        flac.write_bytes(b"x" * 64)  # < INLINE_LIMIT_BYTES -> inline path
        return str(flac)

    flac.write_bytes(b"x" * 64)  # also exists for the backend's audio_path arg

    monkeypatch.setattr(cs, "_encode_chunk_flac", fake_encode)

    # Two generateContent responses in order: speech, then an empty window.
    responses = [_speech_response("[00:00:00.000 --> 00:00:02.000] hello"),
                 _empty_stop_response()]
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        url = req.full_url
        calls.append(url)
        if ":generateContent" in url:
            return _FakeResp(responses.pop(0))
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(cs.urllib.request, "urlopen", fake_urlopen)

    b = _backend()
    # duration 600 s with the default 480 s window -> exactly 2 chunks. The
    # encoder is stubbed so the temp file is never unlinked-from-disk twice
    # (os.unlink tolerates the shared path: second unlink raises OSError which
    # the finally swallows). Provide the duration so no ffprobe runs.
    segs, info = b.transcribe_to_segments(str(flac), duration=600.0)

    # Both chunks were sent; chunk 1's segment survived the empty chunk 2.
    gen_calls = [u for u in calls if ":generateContent" in u]
    assert len(gen_calls) == 2, gen_calls
    assert len(segs) == 1, segs
    assert segs[0]["text"] == "hello"
    assert segs[0]["start"] == 0.0  # chunk 1 starts at global t=0
    assert info.language == ""
