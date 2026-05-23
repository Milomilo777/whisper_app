"""Tests for ``core.config`` — load, save, merge, fallbacks, recent-files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import config as _cfg


def test_load_config_returns_defaults_when_missing() -> None:
    cfg = _cfg.load_config()
    assert cfg["model"]["name"] == "faster-whisper-large-v3"
    assert cfg["output_formats"] == ["srt", "json", "txt"]
    assert cfg["device"] == "auto"
    # Runtime fallback resolved model_path.
    assert cfg["model_path"]


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    cfg = _cfg.load_config()
    cfg["vad_enabled"] = False
    _cfg.save_config(cfg)
    cfg2 = _cfg.load_config()
    assert cfg2["vad_enabled"] is False


def test_corrupt_json_falls_back_to_defaults() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json}", encoding="utf-8")
    cfg = _cfg.load_config()
    # Defaults restored; corrupt file moved to .corrupt.
    assert cfg["model"]["name"] == "faster-whisper-large-v3"
    assert Path(str(path) + ".corrupt").exists()


def test_wrong_type_for_known_key_reverts() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"vad_enabled": "yes"}), encoding="utf-8",
    )
    cfg = _cfg.load_config()
    # Default re-applied (True).
    assert cfg["vad_enabled"] is True


def test_int_to_bool_coerced() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"vad_enabled": 0}), encoding="utf-8",
    )
    cfg = _cfg.load_config()
    assert cfg["vad_enabled"] is False


def test_non_dict_root_falls_back() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1,2,3]", encoding="utf-8")
    cfg = _cfg.load_config()
    assert cfg["model"]["name"] == "faster-whisper-large-v3"


def test_model_path_derived_from_hub_when_blank() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"hub_folder": "/tmp/whisper-hub"}),
        encoding="utf-8",
    )
    cfg = _cfg.load_config()
    assert "/tmp/whisper-hub" in cfg["model_path"].replace("\\", "/")
    assert "models--Systran--faster-whisper-large-v3" in cfg["model_path"]


def test_add_recent_file_dedupes_and_caps() -> None:
    cfg = _cfg.load_config()
    for i in range(7):
        _cfg.add_recent_file(cfg, f"/tmp/file{i}.mp3", limit=5)
    assert cfg["recent_files"][0] == "/tmp/file6.mp3"
    assert len(cfg["recent_files"]) == 5
    # Re-adding existing file moves it to front, doesn't duplicate.
    _cfg.add_recent_file(cfg, "/tmp/file3.mp3", limit=5)
    assert cfg["recent_files"][0] == "/tmp/file3.mp3"
    assert cfg["recent_files"].count("/tmp/file3.mp3") == 1


def test_add_recent_file_blank_is_noop() -> None:
    cfg = _cfg.load_config()
    before = list(cfg.get("recent_files") or [])
    _cfg.add_recent_file(cfg, "", limit=5)
    assert (cfg.get("recent_files") or []) == before


def test_save_config_creates_directory_if_missing() -> None:
    cfg = _cfg.load_config()
    target = Path(_cfg.config_path())
    # Pre-emptively delete the directory.
    if target.parent.exists():
        for f in target.parent.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
        target.parent.rmdir()
    _cfg.save_config(cfg)
    assert target.exists()
