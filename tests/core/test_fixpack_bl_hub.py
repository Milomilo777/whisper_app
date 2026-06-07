"""Backlog fix-pack regressions for core.hub.

Hermetic: no Tk root, no network, no model. Covers the macOS-report edge
where ``model_folder_for`` was handed a non-string ``model_name`` (e.g. a
hand-edited / externally-produced ``{"model": {"name": null}}`` config).
``None.strip()`` raised an uncaught ``AttributeError`` and crashed launch,
because the config-side callers only guard against ``ValueError``. The fix
coerces the bad-input case into the same clean ``ValueError`` the
empty-string check already raises.
"""
from __future__ import annotations

import pytest

from core import hub


def test_model_folder_for_none_name_raises_valueerror(tmp_path):
    """A None model_name must raise ValueError (not AttributeError), so the
    config-layer ``except ValueError`` fallbacks catch it and launch survives.
    """
    with pytest.raises(ValueError):
        hub.model_folder_for(tmp_path, None)  # type: ignore[arg-type]


def test_model_folder_for_non_string_name_raises_valueerror(tmp_path):
    """A non-string model_name (e.g. an int from a hand-edited config) must
    also raise a clean ValueError rather than crashing on ``.strip()``."""
    with pytest.raises(ValueError):
        hub.model_folder_for(tmp_path, 123)  # type: ignore[arg-type]


def test_model_folder_for_none_name_with_empty_hub_raises_valueerror(monkeypatch, tmp_path):
    """The guard must fire on the empty-hub branch too (no hub configured,
    bad name) — still a ValueError, never an AttributeError."""
    from core import config as _cfg
    monkeypatch.setattr(_cfg, "user_cache_dir", lambda: tmp_path)
    with pytest.raises(ValueError):
        hub.model_folder_for(None, None)  # type: ignore[arg-type]


def test_model_folder_for_valid_name_still_works(tmp_path):
    """The guard must not regress the happy path — a normal slug still
    resolves to the expected per-model directory."""
    out = hub.model_folder_for(tmp_path, "faster-whisper-large-v3")
    assert out == tmp_path / "models--Systran--faster-whisper-large-v3"
