"""Tests for the v0.8 multi-model picker registry."""
from __future__ import annotations

import pytest

from core import model_manager as mm


def test_registry_contains_three_models():
    assert set(mm.MODEL_REGISTRY.keys()) == {
        "large-v3",
        "large-v3-turbo",
        "distil-large-v3.5",
    }


def test_default_slug_is_large_v3():
    assert mm.DEFAULT_MODEL_SLUG == "large-v3"
    assert mm.DEFAULT_MODEL_SLUG in mm.MODEL_REGISTRY


def test_list_models_returns_slug_label_pairs():
    items = mm.list_models()
    assert isinstance(items, list)
    assert len(items) == len(mm.MODEL_REGISTRY)
    for slug, label in items:
        assert isinstance(slug, str)
        assert isinstance(label, str)
        assert slug in mm.MODEL_REGISTRY


def test_resolve_model_entry_returns_dict_shape():
    entry = mm.resolve_model_entry("large-v3")
    assert entry is not None
    # Shape must match DEFAULT_CONFIG["model"] so callers can drop it in.
    assert set(entry.keys()) == {"name", "url", "md5"}
    assert entry["name"] == "faster-whisper-large-v3"
    assert entry["url"].endswith(".zip")
    assert entry["md5"].endswith(".md5")


def test_resolve_model_entry_turbo_returns_distinct_urls():
    base = mm.resolve_model_entry("large-v3")
    turbo = mm.resolve_model_entry("large-v3-turbo")
    distil = mm.resolve_model_entry("distil-large-v3.5")
    assert base is not None and turbo is not None and distil is not None
    assert base["url"] != turbo["url"]
    assert base["url"] != distil["url"]
    assert turbo["url"] != distil["url"]
    assert base["name"] != turbo["name"] != distil["name"]


def test_resolve_model_entry_unknown_slug_returns_none():
    assert mm.resolve_model_entry("does-not-exist") is None
    assert mm.resolve_model_entry("") is None


@pytest.mark.parametrize("slug", list(mm.MODEL_REGISTRY.keys()))
def test_every_registry_entry_has_required_fields(slug):
    entry = mm.MODEL_REGISTRY[slug]
    assert "label" in entry and entry["label"]
    assert "name" in entry and entry["name"]
    assert "url" in entry and entry["url"].startswith("https://")
    assert "md5" in entry and entry["md5"].startswith("https://")
    assert "approx_size_gb" in entry
    assert isinstance(entry["approx_size_gb"], (int, float))


def test_label_includes_size_so_user_sees_install_cost():
    """The dropdown label is the only place the user learns the install
    cost; ensure every label includes a GB hint."""
    for _slug, label in mm.list_models():
        assert "GB" in label, f"label {label!r} missing GB size hint"


def test_default_config_carries_new_keys():
    """The new whisper_model + hallucination_detect_enabled keys must
    ship in DEFAULT_CONFIG so a fresh install picks them up without
    needing the user to edit anything."""
    from core.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG.get("whisper_model") == "large-v3"
    assert DEFAULT_CONFIG.get("hallucination_detect_enabled") is True
