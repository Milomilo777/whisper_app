"""Tests for P4-5 ffplay auto-download — pure URL selection + zip extraction.

These exercise the pure seams (no network): the platform->url chooser and the
extract-ffplay-from-zip logic with a tiny in-memory zip, plus the guards when
no URL is configured.
"""
from __future__ import annotations

import io
import os
import zipfile

import pytest

from core import tiling


# --- platform -> url selection ----------------------------------------------

def test_select_ffplay_url_by_key():
    downloads = {
        "windows": "https://example.com/win.zip",
        "macos": "https://example.com/mac.zip",
        "linux": "",
    }
    assert tiling.select_ffplay_url(downloads, "windows") == "https://example.com/win.zip"
    assert tiling.select_ffplay_url(downloads, "macos") == "https://example.com/mac.zip"


def test_select_ffplay_url_empty_value():
    assert tiling.select_ffplay_url({"linux": ""}, "linux") == ""


def test_select_ffplay_url_missing_key():
    assert tiling.select_ffplay_url({"windows": "x"}, "macos") == ""


def test_select_ffplay_url_bad_shape():
    assert tiling.select_ffplay_url(None, "windows") == ""
    assert tiling.select_ffplay_url([], "windows") == ""
    assert tiling.select_ffplay_url({"windows": 123}, "windows") == ""


def test_select_ffplay_url_strips_whitespace():
    assert tiling.select_ffplay_url({"windows": "  https://x  "}, "windows") == "https://x"


def test_platform_key_is_known():
    assert tiling.ffplay_platform_key() in ("windows", "macos", "linux")


# --- extract ffplay from zip ------------------------------------------------

def _make_zip(tmp_path, members: dict[str, bytes]) -> str:
    """Write a zip with the given {arcname: content} and return its path."""
    p = tmp_path / "build.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    p.write_bytes(buf.getvalue())
    return str(p)


def test_extract_ffplay_from_nested_zip(tmp_path):
    exe = tiling._ffplay_exe_name()
    zip_path = _make_zip(tmp_path, {
        "ffmpeg-build/bin/ffmpeg" + (".exe" if exe.endswith(".exe") else ""): b"FFMPEG",
        "ffmpeg-build/bin/" + exe: b"FFPLAY-BINARY",
        "ffmpeg-build/README.txt": b"hi",
    })
    dest = tmp_path / "bin"
    out = tiling.extract_ffplay_from_zip(zip_path, str(dest))
    assert os.path.basename(out) == exe
    assert os.path.isfile(out)
    # Only ffplay was flattened out (not ffmpeg/readme).
    assert open(out, "rb").read() == b"FFPLAY-BINARY"
    assert sorted(os.listdir(dest)) == [exe]


def test_extract_ffplay_accepts_either_name(tmp_path):
    # A Windows zip extracted on a POSIX test host (or vice-versa): the helper
    # accepts ffplay or ffplay.exe by basename.
    zip_path = _make_zip(tmp_path, {"some/path/ffplay.exe": b"WINFFPLAY"})
    dest = tmp_path / "bin"
    out = tiling.extract_ffplay_from_zip(zip_path, str(dest))
    assert open(out, "rb").read() == b"WINFFPLAY"


def test_extract_ffplay_missing_member_raises(tmp_path):
    zip_path = _make_zip(tmp_path, {"bin/ffmpeg": b"x", "bin/ffprobe": b"y"})
    with pytest.raises(FileNotFoundError):
        tiling.extract_ffplay_from_zip(zip_path, str(tmp_path / "bin"))


def test_extract_ffplay_bad_zip_raises(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip at all")
    with pytest.raises(zipfile.BadZipFile):
        tiling.extract_ffplay_from_zip(str(bad), str(tmp_path / "bin"))


# --- download guards (no network) -------------------------------------------

def test_download_ffplay_no_url(monkeypatch):
    msgs = []
    cfg = {"ffplay_downloads": {}}
    ok = tiling.download_ffplay(progress_cb=msgs.append, config=cfg)
    assert ok is False
    assert any("no ffplay download url" in m.lower() for m in msgs)


def test_download_ffplay_rejects_7z(monkeypatch, tmp_path):
    msgs = []
    cfg = {"ffplay_downloads": {tiling.ffplay_platform_key(): "https://x/ffmpeg.7z"}}
    # Should bail BEFORE any network call because .7z is unsupported.
    ok = tiling.download_ffplay(progress_cb=msgs.append, config=cfg)
    assert ok is False
    assert any(".7z" in m or "tar" in m.lower() for m in msgs)


def test_download_ffplay_extracts_local_zip(monkeypatch, tmp_path):
    """End-to-end with the network stubbed: a zip 'download' that contains
    ffplay lands in bin/. Stubs urlopen + bin_dir to stay hermetic."""
    exe = tiling._ffplay_exe_name()
    # A real ffplay binary is several MB; the download guard rejects a
    # < 100 KB extract as truncated, so the stub must be realistically sized.
    payload = b"FFPLAY-OK" + b"\x00" * (110 * 1024)
    src_zip = _make_zip(tmp_path, {"ffmpeg/bin/" + exe: payload})
    bindir = tmp_path / "appbin"

    class _FakeResp:
        def __init__(self, data):
            self._b = io.BytesIO(data)

        def read(self, *a):
            return self._b.read(*a)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    data = open(src_zip, "rb").read()
    monkeypatch.setattr(tiling.urllib.request, "urlopen", lambda *a, **k: _FakeResp(data))
    monkeypatch.setattr(tiling, "bin_dir", lambda: str(bindir))

    cfg = {"ffplay_downloads": {tiling.ffplay_platform_key(): "https://x/build.zip"}}
    ok = tiling.download_ffplay(config=cfg)
    assert ok is True
    assert os.path.isfile(bindir / exe)
    assert open(bindir / exe, "rb").read() == payload


def test_download_ffplay_rejects_truncated_member(monkeypatch, tmp_path):
    """A truncated / near-empty ffplay member (a broken or partial zip
    extract) must NOT be reported as ready, and the unusable stub must be
    removed so bin/ stays 'missing' rather than leaving a broken file that
    a later retry would skip over. Regression for the 0-byte ffplay guard.
    """
    exe = tiling._ffplay_exe_name()
    # 50 bytes — extracts fine, but well under the 100 KB "real binary" floor.
    src_zip = _make_zip(tmp_path, {"ffmpeg/bin/" + exe: b"x" * 50})
    bindir = tmp_path / "appbin"

    class _FakeResp:
        def __init__(self, data):
            self._b = io.BytesIO(data)

        def read(self, *a):
            return self._b.read(*a)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    data = open(src_zip, "rb").read()
    monkeypatch.setattr(tiling.urllib.request, "urlopen", lambda *a, **k: _FakeResp(data))
    monkeypatch.setattr(tiling, "bin_dir", lambda: str(bindir))

    cfg = {"ffplay_downloads": {tiling.ffplay_platform_key(): "https://x/build.zip"}}
    ok = tiling.download_ffplay(config=cfg)
    assert ok is False
    # the broken stub must have been unlinked, not left behind
    assert not os.path.isfile(bindir / exe)
