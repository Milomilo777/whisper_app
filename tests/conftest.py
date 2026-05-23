"""Shared test fixtures.

We point platformdirs at a tmp_path-rooted location for every test so
the hermetic suite never touches the user's real ``%APPDATA%`` and
``%LOCALAPPDATA%`` directories.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_platformdirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect every WhisperProjectBasic platformdirs path to ``tmp_path``."""
    base = tmp_path / "app"
    cfg = base / "config"
    cache = base / "cache"
    logs = base / "logs"
    data = base / "data"
    for p in (cfg, cache, logs, data):
        p.mkdir(parents=True, exist_ok=True)

    # Patch the platformdirs accessors used in core.config.
    from core import config as _cfg

    monkeypatch.setattr(_cfg, "user_config_dir", lambda: cfg)
    monkeypatch.setattr(_cfg, "user_cache_dir", lambda: cache)
    monkeypatch.setattr(_cfg, "user_log_dir", lambda: logs)
    monkeypatch.setattr(_cfg, "user_data_dir", lambda: data)
    # core.logging_setup also imports user_log_dir at module level —
    # re-bind there too so log handlers land in the tmp folder.
    from core import logging_setup as _ls
    monkeypatch.setattr(_ls, "user_log_dir", lambda: logs)

    # And kill the module-level cwd reliance.
    os.environ.pop("WHISPER_WORKER_TOKEN", None)
