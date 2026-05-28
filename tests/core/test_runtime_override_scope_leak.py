"""Audit P2-29: _runtime_overrides_scope must restore the diarisation /
alignment keys that _apply_runtime_overrides unconditionally fills, not
just the keys the project file explicitly set. Otherwise those defaults
leak into the next file the long-lived worker processes.
"""
from __future__ import annotations

import core.transcriber as t
from core.task import TranscriptionTask


_RUNTIME_DEFAULTS = {
    "diarization_enabled": False,
    "diarization_num_speakers": -1,
    "diarization_cluster_threshold": 0.5,
    "alignment": "none",
}


def _patch(monkeypatch, *, overrides):
    # Module config starts WITHOUT any diarisation/alignment keys.
    monkeypatch.setattr(t, "config", {"output_formats": ["srt"]})
    monkeypatch.setattr(t, "load_config", lambda: dict(_RUNTIME_DEFAULTS))
    import core.config as cfg
    monkeypatch.setattr(cfg, "load_project_overrides", lambda _p: dict(overrides))


def test_scope_removes_default_filled_keys_when_no_override(monkeypatch, tmp_path):
    _patch(monkeypatch, overrides={})
    task = TranscriptionTask(str(tmp_path / "a.wav"))

    with t._runtime_overrides_scope(task):
        # Inside the scope _apply_runtime_overrides has filled the defaults.
        assert "diarization_enabled" in t.config

    # On exit the keys it ADDED must be gone — not leaked to the next file.
    for key in _RUNTIME_DEFAULTS:
        assert key not in t.config, f"{key} leaked past the scope"
    assert t.config == {"output_formats": ["srt"]}


def test_scope_restores_diarisation_override_to_prior_value(monkeypatch, tmp_path):
    # A project file for THIS file enables diarisation; the next file
    # (no project file) must not inherit it.
    _patch(monkeypatch, overrides={"diarization_enabled": True})
    task = TranscriptionTask(str(tmp_path / "a.wav"))

    with t._runtime_overrides_scope(task):
        assert t.config["diarization_enabled"] is True  # honoured for this file

    # Restored: the override + the default-filled keys are all gone.
    assert "diarization_enabled" not in t.config
    assert t.config == {"output_formats": ["srt"]}
