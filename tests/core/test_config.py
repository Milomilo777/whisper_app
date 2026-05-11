"""Tests for core.config — load/save round-trip, defaults, fallbacks, migration.

Each test redirects platformdirs through monkeypatch so it never touches the
real user config dir.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core import config as cfg


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Redirect every platformdirs lookup at a tmp_path subfolder."""
    config_dir = tmp_path / "config"
    cache_dir = tmp_path / "cache"
    log_dir = tmp_path / "log"
    data_dir = tmp_path / "data"
    monkeypatch.setattr(cfg, "user_config_dir", lambda: config_dir)
    monkeypatch.setattr(cfg, "user_cache_dir", lambda: cache_dir)
    monkeypatch.setattr(cfg, "user_log_dir", lambda: log_dir)
    monkeypatch.setattr(cfg, "user_data_dir", lambda: data_dir)
    monkeypatch.setattr(cfg, "config_path", lambda: str(config_dir / "config.json"))
    config_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_load_returns_defaults_when_missing(isolated_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json"))
    config = cfg.load_config()
    assert config["theme"] == cfg.DEFAULT_CONFIG["theme"]
    assert config["model"]["name"] == cfg.DEFAULT_CONFIG["model"]["name"]
    assert config["parallel_workers"] == cfg.DEFAULT_CONFIG["parallel_workers"]


def test_save_then_load_roundtrip(isolated_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json"))
    payload = dict(cfg.DEFAULT_CONFIG)
    payload["theme"] = "light"
    payload["parallel_workers"] = 4
    cfg.save_config(payload)
    loaded = cfg.load_config()
    assert loaded["theme"] == "light"
    assert loaded["parallel_workers"] == 4


def test_load_corrupt_json_falls_back(isolated_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json"))
    Path(cfg.config_path()).write_text("{not valid json", encoding="utf-8")
    config = cfg.load_config()
    assert config["theme"] == cfg.DEFAULT_CONFIG["theme"]
    assert os.path.exists(cfg.config_path() + ".corrupt")


def test_load_non_object_json_falls_back(isolated_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json"))
    Path(cfg.config_path()).write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    config = cfg.load_config()
    assert config["theme"] == cfg.DEFAULT_CONFIG["theme"]


def test_user_overrides_merge_with_defaults(isolated_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json"))
    Path(cfg.config_path()).write_text(json.dumps({"theme": "dark", "model": {"name": "tiny"}}), encoding="utf-8")
    config = cfg.load_config()
    assert config["theme"] == "dark"
    assert config["model"]["name"] == "tiny"
    assert config["model"]["url"] == cfg.DEFAULT_CONFIG["model"]["url"]


def test_unmounted_model_path_falls_back(isolated_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json"))
    payload = dict(cfg.DEFAULT_CONFIG)
    payload["model_path"] = "Z:/nonexistent_drive/model"
    Path(cfg.config_path()).write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(cfg, "_drive_is_mounted", lambda p: False)
    config = cfg.load_config()
    assert "Z:/nonexistent_drive" not in config["model_path"]
    assert "models" in config["model_path"]


def test_unmounted_download_folder_clears(isolated_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json"))
    payload = dict(cfg.DEFAULT_CONFIG)
    payload["download_folder"] = "Z:/nonexistent/downloads"
    Path(cfg.config_path()).write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(cfg, "_drive_is_mounted", lambda p: False)
    config = cfg.load_config()
    assert config["download_folder"] == ""


def test_save_is_atomic_no_temp_left_on_success(isolated_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json"))
    cfg.save_config(dict(cfg.DEFAULT_CONFIG))
    leftovers = list(Path(cfg.config_path()).parent.glob(".config-*.tmp"))
    assert leftovers == []


def test_legacy_config_migrates(isolated_dirs, monkeypatch, tmp_path):
    legacy = tmp_path / "old_config.json"
    legacy.write_text(json.dumps({"theme": "light", "log_level": "DEBUG"}), encoding="utf-8")
    monkeypatch.setattr(cfg, "_legacy_config_path", lambda: str(legacy))
    config = cfg.load_config()
    assert config["theme"] == "light"
    assert config["log_level"] == "DEBUG"
    assert (legacy.parent / "old_config.json.migrated.bak").exists()
    assert not legacy.exists()
