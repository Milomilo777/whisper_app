"""Tests for ``core.paths``."""
from __future__ import annotations

import os

from core import paths as _p


def test_resource_base_returns_repo_root_in_source_mode() -> None:
    base = _p.resource_base()
    # Repo root contains gui.py.
    assert os.path.isfile(os.path.join(base, "gui.py"))


def test_bin_dir_under_resource_base() -> None:
    assert _p.bin_dir() == os.path.join(_p.resource_base(), "bin")


def test_bundled_binary_returns_absolute_when_present() -> None:
    path = _p.bundled_binary("ffmpeg")
    # ffmpeg is bundled in this repo so the path should resolve to a file.
    assert os.path.isfile(path)


def test_bundled_binary_falls_back_to_name_when_missing() -> None:
    out = _p.bundled_binary("nonexistent-binary-xyzzy")
    assert out == "nonexistent-binary-xyzzy"
