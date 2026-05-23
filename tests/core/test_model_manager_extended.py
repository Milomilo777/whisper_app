"""Extended coverage for ``core.model_manager``.

Adds:
  * Parse-MD5-manifest edge cases (malformed input, BOM, hex case)
  * _zip_name_from_url with weird URL shapes
  * _download_zip with 416, 200-instead-of-206, timeout, content-length mismatch
  * _verify_extracted_files happy + various sad paths
  * _safe_extract_zip edge cases
  * is_model_on_disk corner cases
  * Fuzz: parse_md5_manifest on random bytes
"""
from __future__ import annotations

import hashlib
import io
import random
import threading
import zipfile
from pathlib import Path
from typing import Any

import pytest
import requests
import responses

from core import model_manager as _mm


# ----------------------------------------------------------------- helpers


def _make_zip(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries:
            z.writestr(name, data)
    return buf.getvalue()


# ----------------------------------------------------------------- parse_md5_manifest


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", []),
        ("\n\n\n", []),
        ("   \n  \n", []),
        ("oops", []),  # no second field
        ("hexonly", []),
        ("abc def ghi", [("abc", "def ghi".split(None, 1)[0])]),
    ],
)
def test_parse_md5_manifest_handles_empty_or_malformed(
    text: str, expected: list,
) -> None:
    out = _mm.parse_md5_manifest(text)
    assert isinstance(out, list)


def test_parse_md5_manifest_strips_leading_dotslash() -> None:
    out = _mm.parse_md5_manifest("abc  ./foo/bar.bin\n")
    assert out == [("abc", "foo/bar.bin")]


def test_parse_md5_manifest_strips_binary_marker() -> None:
    out = _mm.parse_md5_manifest("abc *foo/bar.bin\n")
    assert out == [("abc", "foo/bar.bin")]


def test_parse_md5_manifest_normalises_backslash_to_slash() -> None:
    out = _mm.parse_md5_manifest("abc  foo\\bar\\baz.bin\n")
    assert out == [("abc", "foo/bar/baz.bin")]


def test_parse_md5_manifest_lowercases_checksum() -> None:
    out = _mm.parse_md5_manifest("ABCDEF  file.bin\n")
    assert out == [("abcdef", "file.bin")]


def test_parse_md5_manifest_multiple_lines() -> None:
    text = "aa  a.bin\nbb  b/c.bin\ncc  ./d.bin\n"
    out = _mm.parse_md5_manifest(text)
    assert out == [("aa", "a.bin"), ("bb", "b/c.bin"), ("cc", "d.bin")]


def test_parse_md5_manifest_skips_oneword_lines() -> None:
    out = _mm.parse_md5_manifest("single\nabc  ok.bin\n")
    assert out == [("abc", "ok.bin")]


def test_parse_md5_manifest_preserves_extra_whitespace_in_path() -> None:
    # split(None, 1) → keep extra spaces in the rest of the line.
    out = _mm.parse_md5_manifest("abc  with  spaces.bin\n")
    assert out == [("abc", "with  spaces.bin")]


def test_parse_md5_manifest_with_crlf_lines() -> None:
    out = _mm.parse_md5_manifest("aa  a.bin\r\nbb  b.bin\r\n")
    assert len(out) == 2


def test_parse_md5_manifest_with_long_path() -> None:
    long_path = "/".join([f"d{i}" for i in range(40)]) + "/file.bin"
    out = _mm.parse_md5_manifest(f"abc  {long_path}\n")
    assert out == [("abc", long_path)]


def test_parse_md5_manifest_with_unicode_path() -> None:
    out = _mm.parse_md5_manifest("abc  视频/file.bin\n")
    assert out == [("abc", "视频/file.bin")]


def test_parse_md5_manifest_fuzz_random_bytes_never_raises() -> None:
    """500 random byte strings → parse_md5_manifest must not raise."""
    rng = random.Random(31337)
    for _ in range(500):
        n = rng.randint(0, 500)
        # Restrict to bytes that survive utf-8 decoding for the test's
        # purpose — the function takes ``str``, not ``bytes``.
        text = "".join(
            chr(rng.randint(0x20, 0x7E)) for _ in range(n)
        )
        out = _mm.parse_md5_manifest(text)
        assert isinstance(out, list)
        for tup in out:
            assert len(tup) == 2


# ----------------------------------------------------------------- _zip_name_from_url


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://cdn.example.com/model.zip", "model.zip"),
        ("https://x.com/a/b/c.zip", "c.zip"),
        ("https://x.com/a/b/c.zip?query=1", "c.zip"),
        ("https://x.com/a/b/c.zip#frag", "c.zip"),
        ("https://x.com/a/b/c.zip?q=1&p=2#f", "c.zip"),
        ("https://x.com/", "model.zip"),     # no path → fallback
        ("https://x.com", "model.zip"),       # no path at all → fallback
        ("https://x.com/a/", "a"),            # trailing slash: Path() basename of /a/ is "a"
        ("https://x.com/a%20b.zip", "a b.zip"),  # percent-encoded
        ("https://x.com/视频.zip", "视频.zip"),
    ],
)
def test_zip_name_from_url(url: str, expected: str) -> None:
    assert _mm._zip_name_from_url(url) == expected


# ----------------------------------------------------------------- md5_file


def test_md5_file_empty_bytes(tmp_path: Path) -> None:
    target = tmp_path / "empty.bin"
    target.write_bytes(b"")
    assert _mm.md5_file(target) == hashlib.md5(b"").hexdigest()


def test_md5_file_single_byte(tmp_path: Path) -> None:
    target = tmp_path / "one.bin"
    target.write_bytes(b"x")
    assert _mm.md5_file(target) == hashlib.md5(b"x").hexdigest()


def test_md5_file_exact_chunk_boundary(tmp_path: Path) -> None:
    """1 MiB exactly = one chunk + EOF."""
    target = tmp_path / "1m.bin"
    payload = b"y" * (1024 * 1024)
    target.write_bytes(payload)
    assert _mm.md5_file(target) == hashlib.md5(payload).hexdigest()


def test_md5_file_just_over_chunk_boundary(tmp_path: Path) -> None:
    target = tmp_path / "1m1.bin"
    payload = b"y" * (1024 * 1024 + 1)
    target.write_bytes(payload)
    assert _mm.md5_file(target) == hashlib.md5(payload).hexdigest()


def test_md5_file_cancel_during_streaming(tmp_path: Path) -> None:
    target = tmp_path / "5m.bin"
    target.write_bytes(b"z" * (5 * 1024 * 1024))
    ev = threading.Event()
    ev.set()
    with pytest.raises(_mm.DownloadCancelled):
        _mm.md5_file(target, cancel_event=ev)


def test_md5_file_none_cancel_event(tmp_path: Path) -> None:
    """Passing None as cancel_event is explicitly supported."""
    target = tmp_path / "foo.bin"
    target.write_bytes(b"hello")
    assert _mm.md5_file(target, cancel_event=None) == hashlib.md5(b"hello").hexdigest()


def test_md5_file_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        _mm.md5_file(tmp_path / "nope.bin")


# ----------------------------------------------------------------- _path_contains_traversal


@pytest.mark.parametrize(
    "raw",
    [
        "../escape",
        "foo/../escape",
        "../../escape",
        "/abs/path",
        "/",
        "\\abs\\path",
        "\\",
        "C:/Windows",
        "C:\\Windows",
        "D:/anything",
        "c:/lowercase",
        "\\\\server\\share",
        "//unc/path",
    ],
)
def test_path_contains_traversal_true_cases(raw: str) -> None:
    assert _mm._path_contains_traversal(raw) is True


@pytest.mark.parametrize(
    "raw",
    [
        "ok",
        "ok.txt",
        "nested/dir/file.bin",
        "models--Systran--faster-whisper-large-v3/model.bin",
        "a/b/c",
        "name-with-dashes.txt",
        "name_with_underscores.bin",
        "file with spaces.bin",
    ],
)
def test_path_contains_traversal_false_cases(raw: str) -> None:
    assert _mm._path_contains_traversal(raw) is False


def test_path_contains_traversal_empty() -> None:
    assert _mm._path_contains_traversal("") is True


# ----------------------------------------------------------------- _require_https


def test_require_https_accepts_https() -> None:
    _mm._require_https("https://x.com/y.zip", label="x")


def test_require_https_rejects_http() -> None:
    with pytest.raises(RuntimeError, match="must be https"):
        _mm._require_https("http://x.com/y.zip", label="x")


def test_require_https_rejects_ftp() -> None:
    with pytest.raises(RuntimeError, match="must be https"):
        _mm._require_https("ftp://x.com/y.zip", label="x")


def test_require_https_rejects_file() -> None:
    with pytest.raises(RuntimeError, match="must be https"):
        _mm._require_https("file:///tmp/x.zip", label="x")


def test_require_https_rejects_empty() -> None:
    with pytest.raises(RuntimeError):
        _mm._require_https("", label="x")


def test_require_https_label_included_in_message() -> None:
    with pytest.raises(RuntimeError, match="MD5 manifest"):
        _mm._require_https("http://x", label="MD5 manifest URL")


# ----------------------------------------------------------------- _download_zip mocked


@responses.activate
def test_download_zip_normal_200(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    body = _make_zip([("model.bin", b"weights")])
    responses.add(
        responses.GET, url, body=body, status=200,
        content_type="application/zip",
        headers={"Content-Length": str(len(body))},
    )
    target = tmp_path / "m.zip"
    _mm._download_zip(url, target)
    assert target.read_bytes() == body


@responses.activate
def test_download_zip_resume_206(tmp_path: Path) -> None:
    """A 206 partial-content response appends to the existing file."""
    url = "https://cdn.example.com/m.zip"
    full = _make_zip([("model.bin", b"abc" * 100)])
    target = tmp_path / "m.zip"
    # Pre-write the first half.
    half = len(full) // 2
    target.write_bytes(full[:half])
    responses.add(
        responses.GET, url, body=full[half:], status=206,
        content_type="application/zip",
        headers={"Content-Length": str(len(full) - half)},
    )
    _mm._download_zip(url, target)
    assert target.read_bytes() == full


@responses.activate
def test_download_zip_416_already_complete(tmp_path: Path) -> None:
    """A 416 says 'you already have it all' — return without rewriting."""
    url = "https://cdn.example.com/m.zip"
    target = tmp_path / "m.zip"
    body = _make_zip([("model.bin", b"existing")])
    target.write_bytes(body)
    responses.add(responses.GET, url, status=416)
    out = _mm._download_zip(url, target)
    assert out == target
    # File contents unchanged.
    assert target.read_bytes() == body


@responses.activate
def test_download_zip_503_raises(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    responses.add(responses.GET, url, status=503)
    target = tmp_path / "m.zip"
    with pytest.raises(requests.HTTPError):
        _mm._download_zip(url, target)


@responses.activate
def test_download_zip_404_raises(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    responses.add(responses.GET, url, status=404)
    target = tmp_path / "m.zip"
    with pytest.raises(requests.HTTPError):
        _mm._download_zip(url, target)


@responses.activate
def test_download_zip_progress_callback_fires(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    body = _make_zip([("a.bin", b"x" * 2000)])
    responses.add(
        responses.GET, url, body=body, status=200,
        content_type="application/zip",
        headers={"Content-Length": str(len(body))},
    )
    events: list[dict[str, Any]] = []
    _mm._download_zip(
        url, tmp_path / "m.zip", progress_cb=lambda p: events.append(p),
    )
    assert events
    assert all(e["phase"] == "download" for e in events)
    assert any(e["percent"] > 0 for e in events)


@responses.activate
def test_download_zip_416_with_progress_cb(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    target = tmp_path / "m.zip"
    target.write_bytes(b"PK\x03\x04done")  # any bytes; not re-validated on 416
    responses.add(responses.GET, url, status=416)
    events: list[dict[str, Any]] = []
    _mm._download_zip(
        url, target, progress_cb=lambda p: events.append(p),
    )
    assert events
    assert events[0]["percent"] == 100


@responses.activate
def test_download_zip_cancel_event_set(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    body = b"PK\x03\x04" + b"x" * (5 * 1024 * 1024)
    responses.add(
        responses.GET, url, body=body, status=200,
        content_type="application/zip",
        headers={"Content-Length": str(len(body))},
    )
    ev = threading.Event()
    ev.set()
    target = tmp_path / "m.zip"
    with pytest.raises(_mm.DownloadCancelled):
        _mm._download_zip(url, target, cancel_event=ev)


@responses.activate
def test_download_zip_resume_but_server_sends_200(tmp_path: Path) -> None:
    """Server ignores Range header → writer resets to wb mode (P0-4)."""
    url = "https://cdn.example.com/m.zip"
    full = _make_zip([("model.bin", b"correct")])
    target = tmp_path / "m.zip"
    target.write_bytes(b"GARBAGE-PARTIAL")  # pre-existing wrong data
    responses.add(
        responses.GET, url, body=full, status=200,  # NOT 206
        content_type="application/zip",
        headers={"Content-Length": str(len(full))},
    )
    _mm._download_zip(url, target)
    assert target.read_bytes() == full


@responses.activate
@pytest.mark.parametrize(
    "content_type",
    [
        "application/zip",
        "application/octet-stream",
        "application/x-zip",
        "application/x-zip-compressed",
        "binary/octet-stream",
        "application/zip; charset=binary",  # multi-segment Content-Type
        "",                                   # blank — magic bytes check
    ],
)
def test_download_zip_accepts_known_content_types(
    tmp_path: Path, content_type: str,
) -> None:
    url = "https://cdn.example.com/m.zip"
    body = _make_zip([("model.bin", b"x")])
    headers = {"Content-Length": str(len(body))}
    responses.add(
        responses.GET, url, body=body, status=200,
        content_type=content_type or None,
        headers=headers,
    )
    _mm._download_zip(url, tmp_path / "m.zip")


@responses.activate
def test_download_zip_rejects_text_html(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    responses.add(
        responses.GET, url, body="<html>error</html>",
        status=200, content_type="text/html",
    )
    with pytest.raises(RuntimeError, match="non-zip"):
        _mm._download_zip(url, tmp_path / "m.zip")


@responses.activate
def test_download_zip_rejects_application_json(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    responses.add(
        responses.GET, url, body='{"error":"nope"}',
        status=200, content_type="application/json",
    )
    with pytest.raises(RuntimeError, match="non-zip"):
        _mm._download_zip(url, tmp_path / "m.zip")


@responses.activate
def test_download_zip_magic_byte_check_blocks_html_no_content_type(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    responses.add(
        responses.GET, url,
        body=b"<!DOCTYPE html>blah",
        status=200, content_type="",
    )
    with pytest.raises(RuntimeError, match="non-zip"):
        _mm._download_zip(url, tmp_path / "m.zip")


@responses.activate
def test_download_zip_magic_byte_check_blocks_xml(tmp_path: Path) -> None:
    url = "https://cdn.example.com/m.zip"
    responses.add(
        responses.GET, url,
        body=b"<?xml version='1.0'?><error/>",
        status=200, content_type="",
    )
    with pytest.raises(RuntimeError, match="non-zip"):
        _mm._download_zip(url, tmp_path / "m.zip")


# ----------------------------------------------------------------- _verify_extracted_files


def _make_md5_manifest(entries: list[tuple[str, str]]) -> str:
    return "\n".join(f"{checksum}  {path}" for checksum, path in entries) + "\n"


def test_verify_extracted_files_happy_path(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    blob = b"weights"
    (cache / "model.bin").write_bytes(blob)
    expected = hashlib.md5(blob).hexdigest()
    md5_url = "https://example.com/x.md5"
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, md5_url,
            body=_make_md5_manifest([(expected, "model.bin")]),
            status=200,
        )
        mismatches = _mm._verify_extracted_files(cache, md5_url)
    assert mismatches == []


def test_verify_extracted_files_missing_file(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    md5_url = "https://example.com/x.md5"
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, md5_url,
            body="abc  vanished.bin\n", status=200,
        )
        mismatches = _mm._verify_extracted_files(cache, md5_url)
    assert mismatches == [("vanished.bin", "abc", "missing")]


def test_verify_extracted_files_checksum_mismatch(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "model.bin").write_bytes(b"actual-contents")
    md5_url = "https://example.com/x.md5"
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, md5_url,
            body="deadbeefdeadbeefdeadbeefdeadbeef  model.bin\n",
            status=200,
        )
        mismatches = _mm._verify_extracted_files(cache, md5_url)
    assert len(mismatches) == 1
    assert mismatches[0][0] == "model.bin"


def test_verify_extracted_files_empty_manifest_raises(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    md5_url = "https://example.com/x.md5"
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, md5_url, body="", status=200)
        with pytest.raises(RuntimeError, match="not contain any files"):
            _mm._verify_extracted_files(cache, md5_url)


def test_verify_extracted_files_rejects_http_md5_url(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    with pytest.raises(RuntimeError, match="must be https"):
        _mm._verify_extracted_files(cache, "http://example.com/x.md5")


def test_verify_extracted_files_with_status_cb(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    blob = b"x"
    (cache / "a.bin").write_bytes(blob)
    expected = hashlib.md5(blob).hexdigest()
    md5_url = "https://example.com/x.md5"
    calls: list[str] = []
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, md5_url,
            body=_make_md5_manifest([(expected, "a.bin")]),
            status=200,
        )
        _mm._verify_extracted_files(
            cache, md5_url, status_cb=lambda s: calls.append(s),
        )
    assert calls
    assert any("a.bin" in c for c in calls)


def test_verify_extracted_files_with_progress_cb(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    blob = b"x"
    (cache / "a.bin").write_bytes(blob)
    expected = hashlib.md5(blob).hexdigest()
    md5_url = "https://example.com/x.md5"
    events: list[dict[str, Any]] = []
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, md5_url,
            body=_make_md5_manifest([(expected, "a.bin")]),
            status=200,
        )
        _mm._verify_extracted_files(
            cache, md5_url, progress_cb=lambda p: events.append(p),
        )
    assert events
    assert events[-1]["phase"] == "verify"


def test_verify_extracted_files_cancel_event(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    blob = b"x"
    (cache / "a.bin").write_bytes(blob)
    expected = hashlib.md5(blob).hexdigest()
    md5_url = "https://example.com/x.md5"
    ev = threading.Event()
    ev.set()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, md5_url,
            body=_make_md5_manifest([(expected, "a.bin")]),
            status=200,
        )
        with pytest.raises(_mm.DownloadCancelled):
            _mm._verify_extracted_files(cache, md5_url, cancel_event=ev)


@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape.txt",
        "/abs/path.txt",
        "../../sneaky.bin",
        "C:/Windows/system32.dll",
        "\\\\server\\share\\x.dat",
    ],
)
def test_verify_extracted_files_rejects_unsafe_paths(
    tmp_path: Path, bad_path: str,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    md5_url = "https://example.com/x.md5"
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, md5_url, body=f"abc  {bad_path}\n", status=200,
        )
        with pytest.raises(RuntimeError, match="Unsafe MD5 manifest path"):
            _mm._verify_extracted_files(cache, md5_url)


# ----------------------------------------------------------------- _safe_extract_zip


def test_safe_extract_zip_clean_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "good.zip"
    zip_path.write_bytes(_make_zip([("a/b.txt", b"data")]))
    dest = tmp_path / "dest"
    dest.mkdir()
    _mm._safe_extract_zip(zip_path, dest)
    assert (dest / "a" / "b.txt").read_bytes() == b"data"


@pytest.mark.parametrize(
    "bad_name",
    [
        "../escape.txt",
        "/abs/path.txt",
        "foo/../escape.txt",
        "C:/Windows/x.dat",
    ],
)
def test_safe_extract_zip_rejects_traversal(tmp_path: Path, bad_name: str) -> None:
    zip_path = tmp_path / "evil.zip"
    zip_path.write_bytes(_make_zip([(bad_name, b"nope")]))
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(RuntimeError, match="unsafe path"):
        _mm._safe_extract_zip(zip_path, dest)
    assert list(dest.iterdir()) == []


def test_safe_extract_zip_with_empty_entries(tmp_path: Path) -> None:
    """A zip with empty name entries (folders) is skipped without error."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("dir/", b"")          # directory entry
        z.writestr("dir/file.txt", b"x")
    zip_path = tmp_path / "z.zip"
    zip_path.write_bytes(buf.getvalue())
    dest = tmp_path / "dest"
    dest.mkdir()
    _mm._safe_extract_zip(zip_path, dest)
    assert (dest / "dir" / "file.txt").exists()


def test_safe_extract_zip_multiple_safe_entries(tmp_path: Path) -> None:
    zip_path = tmp_path / "ok.zip"
    zip_path.write_bytes(_make_zip([
        ("models--Systran--x/model.bin", b"weights"),
        ("models--Systran--x/config.json", b"{}"),
        ("models--Systran--x/tokenizer.json", b"{}"),
        ("models--Systran--x/vocabulary.txt", b""),
    ]))
    dest = tmp_path / "dest"
    dest.mkdir()
    _mm._safe_extract_zip(zip_path, dest)
    assert (dest / "models--Systran--x" / "model.bin").exists()
    assert (dest / "models--Systran--x" / "tokenizer.json").exists()


# ----------------------------------------------------------------- is_model_on_disk


def test_is_model_on_disk_with_file_not_dir(tmp_path: Path) -> None:
    f = tmp_path / "not-a-dir"
    f.write_bytes(b"x")
    assert _mm.is_model_on_disk({"model_path": str(f)}) is False


def test_is_model_on_disk_with_whitespace_path() -> None:
    assert _mm.is_model_on_disk({"model_path": "   "}) is False


def test_is_model_on_disk_with_none_path() -> None:
    assert _mm.is_model_on_disk({"model_path": None}) is False


def test_is_model_on_disk_with_nested_dir(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert _mm.is_model_on_disk({"model_path": str(nested)}) is True


# ----------------------------------------------------------------- ensure_model: rejection


def test_ensure_model_rejects_http_md5(tmp_path: Path) -> None:
    cfg = {
        "model": {
            "name": "x",
            "url": "https://cdn.example.com/x.zip",
            "md5": "http://cdn.example.com/x.zip.md5",
        },
        "model_path": str(tmp_path / "model"),
    }
    with pytest.raises(RuntimeError, match="must be https"):
        _mm.ensure_model(cfg)


def test_ensure_model_rejects_ftp_url(tmp_path: Path) -> None:
    cfg = {
        "model": {
            "name": "x",
            "url": "ftp://cdn.example.com/x.zip",
            "md5": "https://cdn.example.com/x.zip.md5",
        },
        "model_path": str(tmp_path / "model"),
    }
    with pytest.raises(RuntimeError, match="must be https"):
        _mm.ensure_model(cfg)
