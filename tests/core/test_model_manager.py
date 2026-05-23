"""Tests for ``core.model_manager`` — parse + verify + md5."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core import model_manager as _mm


def test_parse_md5_manifest_skips_blank_and_short_lines() -> None:
    text = (
        "abc123  model.bin\n"
        "\n"
        "no-second-field\n"
        "deadbeef *binary-mode/path.json\n"
        "feedface  ./normalised.txt\n"
    )
    entries = _mm.parse_md5_manifest(text)
    assert entries == [
        ("abc123", "model.bin"),
        ("deadbeef", "binary-mode/path.json"),
        ("feedface", "normalised.txt"),
    ]


def test_md5_file(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    payload = b"hello world\n" * 10
    target.write_bytes(payload)
    expected = hashlib.md5(payload).hexdigest()
    assert _mm.md5_file(target) == expected


def test_md5_file_respects_cancel(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    target.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB
    import threading
    ev = threading.Event()
    ev.set()
    with pytest.raises(_mm.DownloadCancelled):
        _mm.md5_file(target, cancel_event=ev)


def test_is_model_on_disk_false_when_missing(tmp_path: Path) -> None:
    cfg = {"model_path": str(tmp_path / "nope")}
    assert _mm.is_model_on_disk(cfg) is False


def test_is_model_on_disk_true_when_present(tmp_path: Path) -> None:
    p = tmp_path / "model"
    p.mkdir()
    cfg = {"model_path": str(p)}
    assert _mm.is_model_on_disk(cfg) is True


def test_is_model_on_disk_blank_path_false() -> None:
    assert _mm.is_model_on_disk({"model_path": ""}) is False
    assert _mm.is_model_on_disk({}) is False
