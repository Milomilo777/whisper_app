"""Tests for the Demucs vocal separator wrapper."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core import separator as sep


def test_is_available_false_when_demucs_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "demucs", None)
    assert sep.is_available() is False
    assert "demucs" in sep.availability_reason()


# ---------- behaviour matrix ---------------------------------------------------


def test_separate_vocals_disabled_returns_input(tmp_path):
    src = tmp_path / "audio.wav"
    src.write_bytes(b"riff")
    assert sep.separate_vocals(str(src), enabled=False) == str(src)


def test_separate_vocals_missing_demucs_returns_input(tmp_path, monkeypatch):
    monkeypatch.setattr(sep, "is_available", lambda: False)
    src = tmp_path / "audio.wav"
    src.write_bytes(b"riff")
    logs: list[str] = []
    out = sep.separate_vocals(str(src), enabled=True, log=logs.append)
    assert out == str(src)
    assert any("demucs" in s.lower() for s in logs)


def test_separate_vocals_cache_hit_skips_demucs(tmp_path, monkeypatch):
    src = tmp_path / "audio.wav"
    src.write_bytes(b"\x00" * 4096)
    monkeypatch.setattr(sep, "is_available", lambda: True)
    monkeypatch.setattr(sep, "cache_dir", lambda: tmp_path / "cache")
    # Pre-create the cached vocals stem so the cache-hit branch runs.
    cached = sep._cached_vocals_path(str(src), sep.DEFAULT_MODEL)
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"v" * 4096)
    # If demucs were invoked we'd see a CLI call; trip-wire it.
    monkeypatch.setattr(
        sep, "_run_demucs_cli",
        lambda *a, **kw: pytest.fail("demucs ran on cache hit"),
    )
    out = sep.separate_vocals(str(src), enabled=True)
    assert out == str(cached)


def test_separate_vocals_falls_back_to_input_on_demucs_error(tmp_path, monkeypatch):
    src = tmp_path / "audio.wav"
    src.write_bytes(b"\x00" * 4096)
    monkeypatch.setattr(sep, "is_available", lambda: True)
    monkeypatch.setattr(sep, "cache_dir", lambda: tmp_path / "cache")

    def _boom(*a, **kw):
        raise RuntimeError("demucs exploded")

    monkeypatch.setattr(sep, "_run_demucs_cli", _boom)
    logs: list[str] = []
    out = sep.separate_vocals(str(src), enabled=True, log=logs.append)
    assert out == str(src)
    assert any("demucs" in s.lower() for s in logs)


def test_separate_vocals_caches_run_output(tmp_path, monkeypatch):
    """A successful demucs run must move its vocals.wav into the cache
    so the next call short-circuits."""
    src = tmp_path / "audio.wav"
    src.write_bytes(b"\x00" * 4096)
    monkeypatch.setattr(sep, "is_available", lambda: True)
    cache = tmp_path / "cache"
    monkeypatch.setattr(sep, "cache_dir", lambda: cache)

    def _fake_run(audio_path, out_dir, *, model, log=None):
        # Mimic demucs's typical output layout: out_dir/<model>/<stem>/vocals.wav
        stem_dir = Path(out_dir) / model / Path(audio_path).stem
        stem_dir.mkdir(parents=True, exist_ok=True)
        (stem_dir / "vocals.wav").write_bytes(b"v" * 8192)

    monkeypatch.setattr(sep, "_run_demucs_cli", _fake_run)
    out = sep.separate_vocals(str(src), enabled=True)
    cached = sep._cached_vocals_path(str(src), sep.DEFAULT_MODEL)
    assert out == str(cached)
    assert cached.exists()
    assert cached.read_bytes() == b"v" * 8192


# ---------- cache key ----------------------------------------------------------


def test_cache_key_changes_with_mtime(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"a" * 1024)
    k1 = sep._cache_key(str(p), "htdemucs")
    import os, time
    # Bump mtime by 10 seconds — same path, different cache key.
    new_mtime = p.stat().st_mtime + 10
    os.utime(str(p), (new_mtime, new_mtime))
    k2 = sep._cache_key(str(p), "htdemucs")
    assert k1 != k2


def test_cache_key_differs_per_model(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"a" * 1024)
    k1 = sep._cache_key(str(p), "htdemucs")
    k2 = sep._cache_key(str(p), "mdx_extra")
    assert k1 != k2


def test_cache_key_stable_for_missing_path():
    # Should not crash even when the file doesn't exist.
    k1 = sep._cache_key("/no/such/file.wav", "htdemucs")
    k2 = sep._cache_key("/no/such/file.wav", "htdemucs")
    assert k1 == k2


def test_find_vocals_in_descends_into_subdirs(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    target = nested / "vocals.wav"
    target.write_bytes(b"x")
    found = sep._find_vocals_in(tmp_path)
    assert found == target
