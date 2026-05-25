"""Tests for core.optional_deps (on-demand optional dependency mechanism)."""
from __future__ import annotations

from core import optional_deps


def test_packages_for_known_features():
    assert optional_deps.packages_for("alignment") == ["stable-ts"]
    assert optional_deps.packages_for("whisper_backend") == ["openai-whisper"]


def test_packages_for_unknown_feature_is_empty():
    assert optional_deps.packages_for("nope") == []


def test_extras_dir_ends_in_pylibs():
    assert optional_deps.extras_dir().replace("\\", "/").endswith("/pylibs")


def test_is_available_unknown_feature_is_false():
    # An unknown feature has no module to probe → never available, no raise.
    assert optional_deps.is_available("definitely-not-a-real-feature") is False


def test_install_unknown_feature_is_noop_false():
    # No packages → nothing to install, returns False without spawning pip.
    assert optional_deps.install("nope") is False
