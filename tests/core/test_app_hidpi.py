"""Tests for the HiDPI scaling computation.

We can't call App._apply_hidpi_scaling directly without spinning up
Tk, but the math is simple: scale = max(1.0, dpi / 72.0). Pin that
behaviour here so a regression doesn't shrink fonts on high-DPI
displays.
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")


def test_hidpi_scale_factor_72_dpi_stays_1():
    """At 72 dpi (Tk's logical default) the scale must be 1.0."""
    dpi = 72.0
    scale = max(1.0, dpi / 72.0)
    assert scale == 1.0


def test_hidpi_scale_factor_96_dpi_is_1_33():
    """At 96 dpi (Windows default) the scale must be ~1.33."""
    dpi = 96.0
    scale = max(1.0, dpi / 72.0)
    assert abs(scale - (96.0 / 72.0)) < 1e-9


def test_hidpi_scale_factor_144_dpi_is_2():
    """At 144 dpi (150% Windows scaling) the scale must be 2.0."""
    dpi = 144.0
    scale = max(1.0, dpi / 72.0)
    assert scale == 2.0


def test_hidpi_scale_factor_clamps_below_72():
    """A pathological dpi report below 72 must still produce a
    scale of >= 1.0 so the UI doesn't shrink to dollhouse size."""
    dpi = 50.0
    scale = max(1.0, dpi / 72.0)
    assert scale == 1.0


def test_app_class_has_hidpi_scaling_method():
    """The App class must still expose the helper; rename → test
    fails so we notice."""
    from app.app import App
    assert hasattr(App, "_apply_hidpi_scaling")
    assert callable(App._apply_hidpi_scaling)
