"""Regression: the Video Tiling grid size (tiling_divisions_var) is now persisted
to app_config in _save_tiling_prefs (it was never saved/restored before, so the
grid silently reverted to 3 every launch). The value is clamped, and a junk/empty
Spinbox value (TclError) leaves the prior saved value intact rather than crashing
the save.
"""
from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def app_mod():
    if "faster_whisper" not in sys.modules:
        fw = types.ModuleType("faster_whisper")
        fw.WhisperModel = object  # type: ignore[attr-defined]
        sys.modules["faster_whisper"] = fw
    import app.app as m
    return m


class _Var:
    def __init__(self, v):
        self._v = v

    def get(self):
        if isinstance(self._v, Exception):
            raise self._v
        return self._v


def _app(app_mod, divisions_var):
    a = app_mod.App.__new__(app_mod.App)
    a.app_config = {}
    a.tiling_quality_var = _Var("Auto")
    a.tiling_mute_var = _Var(False)
    a.tiling_multi_monitor_var = _Var(False)
    a.tiling_auto_restart_var = _Var(True)
    a.tiling_divisions_var = divisions_var
    a.tiling_selected_monitors = []
    a.log = lambda *x, **k: None
    return a


def test_save_persists_clamped_divisions(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "save_config", lambda cfg: None)
    a = _app(app_mod, _Var(5))
    app_mod.App._save_tiling_prefs(a)
    assert a.app_config["tiling_divisions"] == 5


def test_save_clamps_out_of_range_divisions(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "save_config", lambda cfg: None)
    a = _app(app_mod, _Var(9999))
    app_mod.App._save_tiling_prefs(a)
    from core.tiling import MAX_DIVISIONS
    assert a.app_config["tiling_divisions"] == MAX_DIVISIONS


def test_save_tolerates_junk_spinbox(app_mod, monkeypatch):
    import tkinter as tk
    monkeypatch.setattr(app_mod, "save_config", lambda cfg: None)
    a = _app(app_mod, _Var(tk.TclError("expected integer")))
    # Must not raise; tiling_divisions simply not written (prior value kept).
    app_mod.App._save_tiling_prefs(a)
    assert "tiling_divisions" not in a.app_config
