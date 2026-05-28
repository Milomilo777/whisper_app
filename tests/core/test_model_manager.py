"""Tests for core.model_manager — pure helpers + ensure_model with mocked HTTP.

Uses ``responses`` to fake the model zip + md5 manifest endpoints. Builds a
trivial in-memory zip whose contents match the manifest, so the full
download → extract → verify happy path runs without touching the network.
"""
from __future__ import annotations

import hashlib
import io
import threading
import zipfile
from pathlib import Path

import pytest
import responses

from core import model_manager as mm


def test_md5_file_matches_hashlib(tmp_path):
    payload = b"the quick brown fox jumps over the lazy dog"
    file = tmp_path / "sample.bin"
    file.write_bytes(payload)
    assert mm.md5_file(file) == hashlib.md5(payload).hexdigest()


def test_md5_file_respects_cancel(tmp_path):
    file = tmp_path / "big.bin"
    file.write_bytes(b"x" * (4 * 1024 * 1024))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(mm.DownloadCancelled):
        mm.md5_file(file, cancel)


def test_zip_name_from_url():
    assert mm._zip_name_from_url("https://example.com/path/model.zip") == "model.zip"
    assert mm._zip_name_from_url("https://example.com/with%20space.zip") == "with space.zip"
    assert mm._zip_name_from_url("https://example.com/") == "model.zip"


def test_parse_md5_manifest_handles_variants():
    # Real md5sum lines begin with a 32-hex digest.
    h1 = "0" * 32
    h2 = "1" * 32
    h3 = "ABCDEF0123456789abcdef0123456789"  # mixed case -> lowercased
    text = f"{h1} *file1.bin\n{h2}  ./sub/file2.bin\n  \n{h3} sub\\file3.bin\n"
    parsed = mm._parse_md5_manifest(text)
    assert (h1, "file1.bin") in parsed
    assert (h2, "sub/file2.bin") in parsed
    assert (h3.lower(), "sub/file3.bin") in parsed


def test_parse_md5_manifest_rejects_non_hex_lines():
    """An HTML / captive-portal body must not be mis-parsed as a manifest
    (it otherwise drives the bounded re-download loop to its cap)."""
    html = "<html><body>Error 407 proxy auth required</body></html>"
    assert mm._parse_md5_manifest(html) == []
    # Short / non-hex tokens are skipped; only a real 32-hex line survives.
    mixed = "abc123 file1.bin\n" + ("d" * 32) + " good.bin\n"
    parsed = mm._parse_md5_manifest(mixed)
    assert parsed == [("d" * 32, "good.bin")]


def test_fmt_bytes_units():
    assert mm._fmt_bytes(0) == "0 B"
    assert mm._fmt_bytes(2048).endswith("KB")
    assert mm._fmt_bytes(5 * 1024 * 1024).endswith("MB")


def test_fmt_time_handles_none_and_negative():
    assert mm._fmt_time(None) == "--:--"
    assert mm._fmt_time(-5) == "00:00"
    assert mm._fmt_time(3661) == "01:01:01"
    assert mm._fmt_time(125) == "02:05"


def _build_model_zip(extract_dir_name: str, files: dict[str, bytes]) -> bytes:
    """Make a zip whose top-level dir is extract_dir_name, containing files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, data in files.items():
            z.writestr(f"{extract_dir_name}/{rel}", data)
    return buf.getvalue()


@responses.activate
def test_ensure_model_full_download_and_verify(tmp_path):
    model_name = "fakemodel"
    model_dir_name = f"models--Systran--{model_name}"
    file_a = b"file-a-bytes"
    file_b = b"file-b-bytes-longer"
    files = {"a.bin": file_a, "sub/b.bin": file_b}

    zip_bytes = _build_model_zip(model_dir_name, files)
    md5_text = "\n".join(
        [
            f"{hashlib.md5(file_a).hexdigest()} {model_dir_name}/a.bin",
            f"{hashlib.md5(file_b).hexdigest()} {model_dir_name}/sub/b.bin",
        ]
    )

    zip_url = "https://fake.test/model.zip"
    md5_url = "https://fake.test/model.md5"

    responses.add(responses.GET, zip_url, body=zip_bytes, status=200,
                  headers={"content-length": str(len(zip_bytes))})
    responses.add(responses.GET, md5_url, body=md5_text, status=200)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    config = {
        "model": {"name": model_name, "url": zip_url, "md5": md5_url},
        "model_path": str(cache_dir / model_dir_name),
    }

    statuses: list[str] = []
    progress_payloads: list[dict] = []
    result = mm.ensure_model(
        config,
        status_cb=statuses.append,
        progress_cb=progress_payloads.append,
    )
    assert Path(result) == cache_dir / model_dir_name
    assert (cache_dir / model_dir_name / "a.bin").read_bytes() == file_a
    assert (cache_dir / model_dir_name / "sub" / "b.bin").read_bytes() == file_b
    assert any(p.get("phase") == "ready" for p in progress_payloads)
    assert any("Model ready" in s for s in statuses)


@responses.activate
def test_ensure_model_already_installed_no_redownload(tmp_path):
    model_name = "fakemodel"
    model_dir_name = f"models--Systran--{model_name}"
    file_a = b"already-here"

    cache_dir = tmp_path / "cache"
    model_dir = cache_dir / model_dir_name
    model_dir.mkdir(parents=True)
    (model_dir / "a.bin").write_bytes(file_a)

    md5_text = f"{hashlib.md5(file_a).hexdigest()} {model_dir_name}/a.bin"
    zip_url = "https://fake.test/model.zip"
    md5_url = "https://fake.test/model.md5"
    responses.add(responses.GET, md5_url, body=md5_text, status=200)
    # Note: zip_url not registered - if ensure_model tries to download we'd see ConnectionError

    config = {
        "model": {"name": model_name, "url": zip_url, "md5": md5_url},
        "model_path": str(model_dir),
    }
    progress_payloads: list[dict] = []
    result = mm.ensure_model(config, progress_cb=progress_payloads.append)
    assert Path(result) == model_dir
    assert any(p.get("phase") == "installed" for p in progress_payloads)


@responses.activate
def test_ensure_model_cancels_on_event(tmp_path):
    model_name = "fakemodel"
    model_dir_name = f"models--Systran--{model_name}"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    cancel = threading.Event()
    cancel.set()

    config = {
        "model": {"name": model_name, "url": "https://fake.test/m.zip", "md5": "https://fake.test/m.md5"},
        "model_path": str(cache_dir / model_dir_name),
    }
    with pytest.raises(mm.DownloadCancelled):
        mm.ensure_model(config, cancel_event=cancel)


def test_unsafe_md5_path_raises(tmp_path):
    """Path traversal attempts in the manifest are rejected."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    md5_url = "https://fake.test/m.md5"
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, md5_url,
                 body=f"{hashlib.md5(b'x').hexdigest()} ../escape.bin\n",
                 status=200)
        with pytest.raises(RuntimeError, match="Unsafe MD5 manifest path"):
            mm._verify_extracted_files(cache_dir, md5_url)


@responses.activate
def test_ensure_model_rejects_zip_slip_member(tmp_path):
    """Audit [15]: a tampered model archive with a traversal member must be
    rejected BEFORE extraction writes anything outside the cache dir."""
    model_name = "fakemodel"
    model_dir_name = f"models--Systran--{model_name}"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{model_dir_name}/ok.bin", b"fine")
        z.writestr("../escape.bin", b"pwned")  # escapes the cache dir
    malicious = buf.getvalue()

    zip_url = "https://fake.test/model.zip"
    md5_url = "https://fake.test/model.md5"
    responses.add(responses.GET, zip_url, body=malicious, status=200,
                  headers={"content-length": str(len(malicious))})
    # The guard fires during extract, before MD5 verification — md5 body
    # is irrelevant, but register it so a stray fetch doesn't ConnectionError.
    responses.add(responses.GET, md5_url, body="", status=200)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    config = {
        "model": {"name": model_name, "url": zip_url, "md5": md5_url},
        "model_path": str(cache_dir / model_dir_name),
    }
    with pytest.raises(RuntimeError, match="Unsafe path in model archive"):
        mm.ensure_model(config)
    # Nothing escaped the cache dir.
    assert not (tmp_path / "escape.bin").exists()


@responses.activate
def test_ensure_model_bounded_retry_raises(tmp_path):
    """Audit [9]: a permanently-mismatching mirror must NOT re-download
    forever — after MAX_DOWNLOAD_ATTEMPTS it raises a terminal error."""
    model_name = "fakemodel"
    model_dir_name = f"models--Systran--{model_name}"
    files = {"a.bin": b"actual-bytes"}
    zip_bytes = _build_model_zip(model_dir_name, files)
    # md5 lists a DIFFERENT digest → every verify mismatches.
    md5_text = f"{hashlib.md5(b'WRONG').hexdigest()} {model_dir_name}/a.bin"

    zip_url = "https://fake.test/model.zip"
    md5_url = "https://fake.test/model.md5"
    responses.add(responses.GET, zip_url, body=zip_bytes, status=200,
                  headers={"content-length": str(len(zip_bytes))})
    responses.add(responses.GET, md5_url, body=md5_text, status=200)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    config = {
        "model": {"name": model_name, "url": zip_url, "md5": md5_url},
        "model_path": str(cache_dir / model_dir_name),
    }
    with pytest.raises(RuntimeError, match="after .* attempts"):
        mm.ensure_model(config)
