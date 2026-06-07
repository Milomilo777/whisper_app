"""Backlog fix-pack regression tests for core.config (cluster: config).

Hermetic: no Tk root, no network, no model. platformdirs are redirected
through a tmp_path fixture so nothing touches the real user config dir.

Covers the one REAL backlog candidate fixed in this cluster:

  * ``_persistable_download_folder`` re-read the raw on-disk config with a
    bare ``json.load`` (no ``parse_constant``), bypassing the non-finite
    guard that ``_read_local_config`` / ``fetch_online_config`` already
    apply. A config file with an ``Infinity`` / ``NaN`` literal in
    ``download_folder`` therefore parsed successfully and then crashed the
    ``.strip()`` with an uncaught ``AttributeError``. The fix mirrors the
    ``parse_constant=_reject_nonfinite`` guard so such a file is treated as
    corrupt (ValueError, already handled) and we fall back cleanly.
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


def _write_raw(text: str) -> None:
    Path(cfg.config_path()).write_text(text, encoding="utf-8")


def test_persistable_download_folder_rejects_nonfinite_on_disk(
    isolated_dirs,
):
    """A non-finite literal in the on-disk download_folder must not crash.

    Without the parse_constant guard, the bare json.load accepts
    ``{"download_folder": Infinity}``, then ``(value or "").strip()``
    raises an uncaught AttributeError on the float. The guard turns it
    into a ValueError that the existing ``except`` swallows, so we fall
    back to the in-memory value instead.
    """
    _write_raw('{"download_folder": Infinity}')
    # In-memory value is empty (the unmounted-drive repair case), so the
    # function would otherwise consult the on-disk file.
    result = cfg._persistable_download_folder({"download_folder": ""})
    assert result == ""


def test_persistable_download_folder_rejects_nan_on_disk(isolated_dirs):
    _write_raw('{"download_folder": NaN}')
    result = cfg._persistable_download_folder({"download_folder": ""})
    assert result == ""


def test_save_config_survives_nonfinite_on_disk(isolated_dirs):
    """save_config must not crash when the existing config.json holds a
    non-finite literal; it overwrites the file with a clean dict."""
    _write_raw('{"download_folder": Infinity}')
    payload = dict(cfg.DEFAULT_CONFIG)
    payload["download_folder"] = ""
    cfg.save_config(payload)  # must not raise
    on_disk = json.loads(
        Path(cfg.config_path()).read_text(encoding="utf-8")
    )
    assert on_disk["download_folder"] == ""


def test_persistable_download_folder_in_memory_value_wins(isolated_dirs):
    """A present in-memory value short-circuits before any disk read, so a
    poisoned file is never even opened."""
    _write_raw('{"download_folder": Infinity}')
    result = cfg._persistable_download_folder(
        {"download_folder": "  C:/dl  "}
    )
    assert result == "C:/dl"


def test_persistable_download_folder_keeps_unmounted_prior(
    isolated_dirs, monkeypatch
):
    """The legitimate path is preserved: a valid on-disk value on a
    currently-unmounted drive is returned (the fix must not break this)."""
    _write_raw(json.dumps({"download_folder": "Z:/recordings"}))
    monkeypatch.setattr(cfg, "_drive_is_mounted", lambda p: False)
    result = cfg._persistable_download_folder({"download_folder": ""})
    assert result == "Z:/recordings"
