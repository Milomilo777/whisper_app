"""Shared test fixtures.

We point platformdirs at a tmp_path-rooted location for every test so
the hermetic suite never touches the user's real ``%APPDATA%`` and
``%LOCALAPPDATA%`` directories.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# Pre-import ctranslate2 and torch ONCE at conftest-load so subsequent
# tests that do `monkeypatch.setattr("builtins.__import__", ...)` and
# then pop the modules from sys.modules can't trigger a second native
# load. On Python 3.14, re-loading torch in mid-process causes an
# access violation in DLL init code. Pre-load = hold a permanent
# reference that survives any sys.modules surgery.
_PRELOADED_CT = None
_PRELOADED_TORCH = None
try:  # pragma: no cover — best-effort warm-up
    import ctranslate2 as _PRELOADED_CT  # noqa: F401
except ImportError:
    pass
try:  # pragma: no cover
    import torch as _PRELOADED_TORCH  # noqa: F401
except ImportError:
    pass


@pytest.fixture(autouse=True)
def _restore_cuda_module_imports() -> None:
    """If a test popped ctranslate2 / torch from sys.modules, put the
    pre-loaded reference back BEFORE the next test runs. Otherwise a
    fresh `import ctranslate2` on Python 3.14 re-runs the native DLL
    initialiser, which crashes with an access violation.
    """
    yield
    if _PRELOADED_CT is not None and "ctranslate2" not in sys.modules:
        sys.modules["ctranslate2"] = _PRELOADED_CT
    if _PRELOADED_TORCH is not None and "torch" not in sys.modules:
        sys.modules["torch"] = _PRELOADED_TORCH


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
