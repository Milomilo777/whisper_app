"""Tests for the model-download hardening (P0-4, P1-1/2/3/4/20).

Uses ``responses`` for HTTP mocking + a hand-built zip for the
extraction tests.
"""
from __future__ import annotations

import hashlib
import io
import threading
import zipfile
from pathlib import Path
from typing import Any

import pytest
import responses

from core import model_manager as _mm


# ---------------------------------------------------------------- helpers

def _make_zip(entries: list[tuple[str, bytes]]) -> bytes:
    """Build an in-memory zip with the given ``(name, data)`` entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries:
            z.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------- P1-20

def test_require_https_rejects_http() -> None:
    with pytest.raises(RuntimeError, match="must be https"):
        _mm._require_https("http://example.com/model.zip", label="model URL")


def test_require_https_rejects_empty() -> None:
    with pytest.raises(RuntimeError):
        _mm._require_https("", label="model URL")


def test_require_https_accepts_https() -> None:
    _mm._require_https("https://example.com/model.zip", label="model URL")


def test_ensure_model_rejects_http_before_any_io(tmp_path: Path) -> None:
    """http:// URL must raise BEFORE any network call.

    We don't set up any responses — if the function tries to fetch,
    ``responses`` would either error out or hit a connection refused.
    """
    cfg = {
        "model": {
            "name": "x",
            "url": "http://cdn.example.com/x.zip",
            "md5": "https://cdn.example.com/x.zip.md5",
        },
        "model_path": str(tmp_path / "model"),
    }
    with pytest.raises(RuntimeError, match="must be https"):
        _mm.ensure_model(cfg)


# ---------------------------------------------------------------- P1-1

def test_path_contains_traversal() -> None:
    assert _mm._path_contains_traversal("../escape")
    assert _mm._path_contains_traversal("foo/../escape")
    assert _mm._path_contains_traversal("/abs/path")
    assert _mm._path_contains_traversal("C:/Windows")
    assert _mm._path_contains_traversal("\\\\server\\share\\x")
    assert not _mm._path_contains_traversal("ok/file.txt")
    assert not _mm._path_contains_traversal("nested/dir/file.bin")


def test_verify_extracted_files_rejects_symlinked_parent(
    tmp_path: Path,
) -> None:
    """A symlink in the path → RuntimeError, no file MD5 calculated."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    real_target = tmp_path / "outside"
    real_target.mkdir()
    (real_target / "secret.bin").write_bytes(b"secret")

    # Plant a symlink inside the cache pointing outside.
    link = cache_dir / "sneaky"
    try:
        link.symlink_to(real_target, target_is_directory=True)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"symlink unsupported on this host: {e}")

    md5_url = "https://example.com/x.md5"
    expected_md5 = hashlib.md5(b"secret").hexdigest()

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, md5_url,
            body=f"{expected_md5}  sneaky/secret.bin\n",
            status=200,
        )
        with pytest.raises(RuntimeError, match="symlink"):
            _mm._verify_extracted_files(cache_dir, md5_url)


def test_verify_extracted_files_rejects_dotdot_manifest_entry(
    tmp_path: Path,
) -> None:
    """A manifest entry with ``..`` is rejected before any resolve()."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    md5_url = "https://example.com/x.md5"

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, md5_url,
            body="abcdef  ../escape.txt\n",
            status=200,
        )
        with pytest.raises(RuntimeError, match="Unsafe MD5 manifest path"):
            _mm._verify_extracted_files(cache_dir, md5_url)


# ---------------------------------------------------------------- P1-2

def test_safe_extract_zip_rejects_traversal(tmp_path: Path) -> None:
    """A zip with ``../escape.txt`` is refused, nothing written."""
    zip_path = tmp_path / "evil.zip"
    zip_path.write_bytes(_make_zip([("../escape.txt", b"nope")]))
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(RuntimeError, match="unsafe path"):
        _mm._safe_extract_zip(zip_path, dest)
    # Nothing landed inside dest, nothing landed in dest.parent either.
    assert list(dest.iterdir()) == []
    assert not (tmp_path / "escape.txt").exists()


def test_safe_extract_zip_accepts_safe_zip(tmp_path: Path) -> None:
    """A clean zip extracts normally."""
    zip_path = tmp_path / "good.zip"
    zip_path.write_bytes(_make_zip([
        ("models--Systran--faster-whisper-large-v3/model.bin", b"weights"),
        ("models--Systran--faster-whisper-large-v3/config.json", b"{}"),
    ]))
    dest = tmp_path / "dest"
    dest.mkdir()
    _mm._safe_extract_zip(zip_path, dest)
    assert (
        dest / "models--Systran--faster-whisper-large-v3" / "model.bin"
    ).read_bytes() == b"weights"


# ---------------------------------------------------------------- P1-3

@responses.activate
def test_download_zip_rejects_html_via_content_type(tmp_path: Path) -> None:
    """A 200 with Content-Type: text/html aborts before writing."""
    url = "https://cdn.example.com/model.zip"
    responses.add(
        responses.GET, url,
        body="<!DOCTYPE html><html><body>Error 502</body></html>",
        status=200,
        content_type="text/html",
    )
    zip_path = tmp_path / "model.zip"
    with pytest.raises(RuntimeError, match="non-zip content"):
        _mm._download_zip(url, zip_path)


@responses.activate
def test_download_zip_rejects_html_via_magic_bytes(tmp_path: Path) -> None:
    """When Content-Type is missing, the first-4-byte magic check catches HTML."""
    url = "https://cdn.example.com/model.zip"
    responses.add(
        responses.GET, url,
        body=b"<!DOCTYPE html><html><body>oops</body></html>",
        status=200,
        # No content_type → falls through to magic-byte check.
        content_type="",
    )
    zip_path = tmp_path / "model.zip"
    with pytest.raises(RuntimeError, match="non-zip content"):
        _mm._download_zip(url, zip_path)


# ---------------------------------------------------------------- P0-4

@responses.activate
def test_download_zip_resets_on_200_no_range_support(tmp_path: Path) -> None:
    """An existing partial + server returning 200 (no Range) → file is
    rewritten in ``wb`` mode, not appended."""
    url = "https://cdn.example.com/model.zip"
    full = _make_zip([("model.bin", b"correct-weights")])

    # Pre-existing partial download (some old garbage).
    zip_path = tmp_path / "model.zip"
    zip_path.write_bytes(b"OLD-PARTIAL-GARBAGE-DATA")

    responses.add(
        responses.GET, url,
        body=full,
        status=200,  # Server ignored Range and sent full body.
        content_type="application/zip",
        headers={"Content-Length": str(len(full))},
    )

    _mm._download_zip(url, zip_path)

    # The written file must equal the full body, NOT (garbage + full).
    assert zip_path.read_bytes() == full


# ---------------------------------------------------------------- P1-4

@responses.activate
def test_ensure_model_caps_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A persistent MD5 mismatch raises RuntimeError after max_retries."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    model_dir = cache_dir / "models--Systran--faster-whisper-large-v3"
    zip_url = "https://cdn.example.com/m.zip"
    md5_url = "https://cdn.example.com/m.zip.md5"

    # The zip extracts a model.bin with content b"actual" but the
    # manifest claims md5 of b"expected" — a permanent mismatch.
    payload = _make_zip([
        ("models--Systran--faster-whisper-large-v3/model.bin", b"actual"),
    ])
    wrong_md5 = hashlib.md5(b"expected").hexdigest()
    # Each retry re-downloads, so register multiple identical responses.
    for _ in range(5):
        responses.add(
            responses.GET, zip_url,
            body=payload, status=200,
            content_type="application/zip",
            headers={"Content-Length": str(len(payload))},
        )
        responses.add(
            responses.GET, md5_url,
            body=f"{wrong_md5}  models--Systran--faster-whisper-large-v3/model.bin\n",
            status=200,
        )

    cfg = {
        "model": {"name": "x", "url": zip_url, "md5": md5_url},
        "model_path": str(model_dir),
    }
    with pytest.raises(RuntimeError, match="MD5 mismatch persisted"):
        _mm.ensure_model(cfg, max_retries=2)
