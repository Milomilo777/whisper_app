"""Regression tests for the configdl fixpack defect.

``save_config`` (via ``_persistable_download_folder``) used to crash with
an uncaught ``AttributeError`` when ``download_folder`` was a non-string
but truthy/finite value (e.g. an int or a list). ``(value or "").strip()``
calls a string method on the non-string, raising. The sibling
``model.name`` path was already guarded with ``isinstance(..., str)``;
``download_folder`` was not. The fix coerces a non-string value to "".

These tests fail on the pre-fix code (AttributeError) and pass after.
They are hermetic: no network, no model, no Tk root — platformdirs is
redirected at a tmp_path, exactly like tests/core/test_config.py.
"""
from __future__ import annotations

import json
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
    monkeypatch.setattr(
        cfg, "config_path", lambda: str(config_dir / "config.json")
    )
    config_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.mark.parametrize("bad_value", [123, [1, 2, 3], 4.5])
def test_save_config_with_non_string_in_memory_download_folder(
    isolated_dirs, monkeypatch, bad_value
):
    """An in-memory non-string download_folder must not crash save_config.

    Pre-fix: ``(123 or "").strip()`` raised AttributeError on the
    in-memory value. The bad value normalises to "" and persists.
    """
    monkeypatch.setattr(
        cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json")
    )
    payload = dict(cfg.DEFAULT_CONFIG)
    payload["download_folder"] = bad_value

    cfg.save_config(payload)  # must not raise

    on_disk = json.loads(Path(cfg.config_path()).read_text(encoding="utf-8"))
    assert on_disk["download_folder"] == ""


@pytest.mark.parametrize("bad_value", [123, [1, 2, 3]])
def test_save_config_with_non_string_on_disk_download_folder(
    isolated_dirs, monkeypatch, bad_value
):
    """A non-string download_folder already on disk must not crash save.

    The in-memory value is empty (so the on-disk fallback path runs),
    and the on-disk value is a non-string. Pre-fix: line ~873's
    ``(on_disk.get("download_folder") or "").strip()`` raised
    AttributeError. The bad on-disk value normalises to "".
    """
    monkeypatch.setattr(
        cfg, "_legacy_config_path", lambda: str(isolated_dirs / "no_legacy.json")
    )
    # Plant a corrupt non-string download_folder directly on disk.
    on_disk_payload = dict(cfg.DEFAULT_CONFIG)
    on_disk_payload["download_folder"] = bad_value
    Path(cfg.config_path()).write_text(
        json.dumps(on_disk_payload), encoding="utf-8"
    )
    # In-memory value is empty -> save consults the on-disk fallback.
    monkeypatch.setattr(cfg, "_drive_is_mounted", lambda p: False)
    config = dict(cfg.DEFAULT_CONFIG)
    config["download_folder"] = ""

    cfg.save_config(config)  # must not raise

    reloaded = json.loads(Path(cfg.config_path()).read_text(encoding="utf-8"))
    assert reloaded["download_folder"] == ""


def test_persistable_download_folder_returns_empty_for_non_string(isolated_dirs):
    """Direct unit check: a non-string in-memory value yields "" (no raise)."""
    assert _result_is_empty({"download_folder": 123})
    assert _result_is_empty({"download_folder": [1, 2, 3]})


def _result_is_empty(config: dict) -> bool:
    return cfg._persistable_download_folder(config) == ""
