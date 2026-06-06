"""Hermetic regression tests for the cloud-STT fixpack.

Covers two hardening fixes in ``core/backends/cloud_stt.py``:

  * SECURITY — the Gemini API key must travel in the ``x-goog-api-key``
    request HEADER, never in the request URL query string (a URL is logged
    by urllib exceptions, proxies, redirects, and server access logs; a
    header is not).
  * PRIVACY — an uploaded Files-API blob must be DELETEd after the chunk is
    transcribed, success or failure, so the user's audio is not left on
    Google's servers.

NO network, NO API key, NO model, NO Tk. ``urllib.request.urlopen`` is
stubbed to record every request and hand back canned responses.
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


def _make_urlopen(recorder: list[Any], responder):
    """Build a fake urlopen that records each Request and delegates to
    ``responder(req)`` for the canned reply (which may raise)."""

    def _urlopen(req, timeout=None):  # noqa: ANN001
        recorder.append(req)
        return responder(req)

    return _urlopen


def _backend() -> cs.CloudSttBackend:
    b = cs.CloudSttBackend(
        config={"cloud_stt_api_key": "SECRET-KEY-123", "cloud_stt_model": "m"}
    )
    assert b.load() is True
    return b


# ---------------------------------------------------------------- security


def test_key_never_in_any_request_url_inline(monkeypatch, tmp_path):
    """Inline (small chunk) path: key in header, not URL."""
    flac = tmp_path / "c.flac"
    flac.write_bytes(b"x" * 100)  # tiny -> inline path

    recorded: list[Any] = []

    def responder(req):  # noqa: ANN001
        body = json.dumps(
            {"candidates": [{"content": {"parts": [{"text":
                "[00:00:00.000 --> 00:00:01.000] hi"}]}, "finishReason": "STOP"}]}
        ).encode("utf-8")
        return _FakeResp(body)

    monkeypatch.setattr(cs.urllib.request, "urlopen", _make_urlopen(recorded, responder))

    b = _backend()
    out = b._transcribe_one_chunk(str(flac), "prompt")
    assert "hi" in out

    assert len(recorded) == 1
    req = recorded[0]
    assert "key=" not in req.full_url
    assert "SECRET-KEY-123" not in req.full_url
    # The key rides in the dedicated header instead.
    assert req.get_header(cs.API_KEY_HEADER.capitalize()) == "SECRET-KEY-123"


def test_key_never_in_url_on_files_api_path(monkeypatch, tmp_path):
    """Large chunk -> Files API: start, upload, generate, delete URLs are
    all key-free, and every request carries the key header."""
    flac = tmp_path / "big.flac"
    flac.write_bytes(b"x" * (cs.INLINE_LIMIT_BYTES + 10))  # forces upload

    recorded: list[Any] = []

    def responder(req):  # noqa: ANN001
        url = req.full_url
        if url.endswith("/upload/v1beta/files"):
            # start: return the resumable upload URL
            return _FakeResp(b"", {"X-Goog-Upload-URL": "https://upload.example/session"})
        if url == "https://upload.example/session":
            # upload+finalize: return the file object
            meta = {"file": {"uri": "https://files/abc", "name": "files/abc",
                             "state": "ACTIVE"}}
            return _FakeResp(json.dumps(meta).encode("utf-8"))
        if ":generateContent" in url:
            body = json.dumps(
                {"candidates": [{"content": {"parts": [{"text":
                    "[00:00:00.000 --> 00:00:01.000] ok"}]},
                    "finishReason": "STOP"}]}
            ).encode("utf-8")
            return _FakeResp(body)
        if req.get_method() == "DELETE":
            return _FakeResp(b"{}")
        raise AssertionError(f"unexpected request: {req.get_method()} {url}")

    monkeypatch.setattr(cs.urllib.request, "urlopen", _make_urlopen(recorded, responder))

    b = _backend()
    out = b._transcribe_one_chunk(str(flac), "prompt")
    assert "ok" in out

    # No request URL ever contains the key.
    for req in recorded:
        assert "key=" not in req.full_url, req.full_url
        assert "SECRET-KEY-123" not in req.full_url, req.full_url

    # The start, generate, and delete requests (those we authenticate) carry
    # the key header. The opaque resumable-upload session URL is
    # Google-issued and authenticated by the start call.
    keyed = [
        r for r in recorded
        if r.full_url != "https://upload.example/session"
    ]
    assert keyed, "expected at least one keyed request"
    for r in keyed:
        assert r.get_header(cs.API_KEY_HEADER.capitalize()) == "SECRET-KEY-123"


def test_ping_key_uses_header_not_url(monkeypatch):
    recorded: list[Any] = []
    monkeypatch.setattr(
        cs.urllib.request, "urlopen",
        _make_urlopen(recorded, lambda req: _FakeResp(b"{}")),
    )
    b = _backend()
    ok, _msg = b.ping_key()
    assert ok is True
    assert len(recorded) == 1
    req = recorded[0]
    assert "key=" not in req.full_url
    assert "SECRET-KEY-123" not in req.full_url
    assert req.get_header(cs.API_KEY_HEADER.capitalize()) == "SECRET-KEY-123"


# ---------------------------------------------------------------- privacy


def test_uploaded_file_is_deleted_after_success(monkeypatch, tmp_path):
    flac = tmp_path / "big.flac"
    flac.write_bytes(b"x" * (cs.INLINE_LIMIT_BYTES + 10))

    recorded: list[Any] = []

    def responder(req):  # noqa: ANN001
        url = req.full_url
        if url.endswith("/upload/v1beta/files"):
            return _FakeResp(b"", {"X-Goog-Upload-URL": "https://upload.example/session"})
        if url == "https://upload.example/session":
            meta = {"file": {"uri": "https://files/abc", "name": "files/abc",
                             "state": "ACTIVE"}}
            return _FakeResp(json.dumps(meta).encode("utf-8"))
        if ":generateContent" in url:
            body = json.dumps(
                {"candidates": [{"content": {"parts": [{"text":
                    "[00:00:00.000 --> 00:00:01.000] ok"}]},
                    "finishReason": "STOP"}]}
            ).encode("utf-8")
            return _FakeResp(body)
        if req.get_method() == "DELETE":
            return _FakeResp(b"{}")
        raise AssertionError(f"unexpected: {url}")

    monkeypatch.setattr(cs.urllib.request, "urlopen", _make_urlopen(recorded, responder))

    b = _backend()
    b._transcribe_one_chunk(str(flac), "prompt")

    deletes = [r for r in recorded if r.get_method() == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0].full_url.endswith("/v1beta/files/abc")


def test_uploaded_file_is_deleted_even_when_generate_fails(monkeypatch, tmp_path):
    """The DELETE runs in a finally — a failed generateContent must still
    clean up the user's audio on Google."""
    flac = tmp_path / "big.flac"
    flac.write_bytes(b"x" * (cs.INLINE_LIMIT_BYTES + 10))

    recorded: list[Any] = []

    def responder(req):  # noqa: ANN001
        url = req.full_url
        if url.endswith("/upload/v1beta/files"):
            return _FakeResp(b"", {"X-Goog-Upload-URL": "https://upload.example/session"})
        if url == "https://upload.example/session":
            meta = {"file": {"uri": "https://files/zzz", "name": "files/zzz",
                             "state": "ACTIVE"}}
            return _FakeResp(json.dumps(meta).encode("utf-8"))
        if ":generateContent" in url:
            # Model returns a hard error -> extract_text_from_response raises.
            return _FakeResp(json.dumps({"error": {"message": "boom"}}).encode("utf-8"))
        if req.get_method() == "DELETE":
            return _FakeResp(b"{}")
        raise AssertionError(f"unexpected: {url}")

    monkeypatch.setattr(cs.urllib.request, "urlopen", _make_urlopen(recorded, responder))

    b = _backend()
    with pytest.raises(RuntimeError):
        b._transcribe_one_chunk(str(flac), "prompt")

    deletes = [r for r in recorded if r.get_method() == "DELETE"]
    assert len(deletes) == 1, "uploaded blob must be deleted even on failure"
    assert deletes[0].full_url.endswith("/v1beta/files/zzz")


def test_delete_failure_is_swallowed(monkeypatch):
    """A failed cleanup must never propagate."""
    import urllib.error

    def boom(req, timeout=None):  # noqa: ANN001
        raise urllib.error.URLError("network down")

    monkeypatch.setattr(cs.urllib.request, "urlopen", boom)
    b = _backend()
    # Must not raise.
    b._delete_file("files/abc")


def test_delete_noop_without_name_or_key(monkeypatch):
    called: list[Any] = []
    monkeypatch.setattr(
        cs.urllib.request, "urlopen",
        _make_urlopen(called, lambda req: _FakeResp(b"{}")),
    )
    b = _backend()
    b._delete_file(None)
    b._delete_file("")
    assert called == []  # no network call for an empty file name
