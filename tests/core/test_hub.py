"""Tests for ``core.hub``."""
from __future__ import annotations

from pathlib import Path

import pytest

from core import hub as _hub


def test_default_hub_folder_under_app_dir() -> None:
    p = _hub.default_hub_folder()
    assert p.name == "hub"
    assert p.parent == _hub.resolve_app_dir()


def test_is_hub_configured_empty_string_false() -> None:
    assert _hub.is_hub_configured({}) is False
    assert _hub.is_hub_configured({"hub_folder": ""}) is False
    assert _hub.is_hub_configured({"hub_folder": "   "}) is False


def test_is_hub_configured_real_path_true() -> None:
    assert _hub.is_hub_configured({"hub_folder": "/tmp/foo"}) is True


def test_normalise_hub_path_empty_returns_default() -> None:
    assert _hub.normalise_hub_path("") == str(_hub.default_hub_folder())


def test_normalise_hub_path_strips_and_absolutizes(tmp_path: Path) -> None:
    raw = f"   {tmp_path}   "
    out = _hub.normalise_hub_path(raw)
    assert out == str(tmp_path.resolve())


def test_model_folder_for_prepends_systran_prefix(tmp_path: Path) -> None:
    out = _hub.model_folder_for(tmp_path, "faster-whisper-large-v3")
    assert out == tmp_path / "models--Systran--faster-whisper-large-v3"


def test_model_folder_for_keeps_full_slug(tmp_path: Path) -> None:
    out = _hub.model_folder_for(tmp_path, "models--OpenAI--whisper-tiny")
    assert out == tmp_path / "models--OpenAI--whisper-tiny"


def test_model_folder_for_empty_name_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _hub.model_folder_for(tmp_path, "")


def test_model_folder_for_no_hub_uses_user_cache(tmp_path: Path) -> None:
    out = _hub.model_folder_for(None, "faster-whisper-large-v3")
    # The autouse fixture redirects user_cache_dir to tmp_path/app/cache.
    assert "models" in out.parts
