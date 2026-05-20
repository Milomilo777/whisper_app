"""Tests for the system-tray controller helpers."""
from __future__ import annotations

import sys
import types

import pytest


def test_is_available_returns_false_without_pystray(monkeypatch):
    # Force pystray import to fail.
    monkeypatch.setitem(sys.modules, "pystray", None)
    from app.widgets import tray
    assert tray.is_available() is False
    assert "pystray" in tray.availability_reason()


def test_controller_without_pystray_is_no_op(monkeypatch):
    """If pystray is missing, TrayController.start / stop / set_active
    must not raise."""
    fake_app = types.SimpleNamespace(after=lambda _ms, _fn: None, log=lambda _m: None)
    monkeypatch.setitem(sys.modules, "pystray", None)
    from app.widgets import tray
    c = tray.TrayController(fake_app)  # type: ignore[arg-type]
    assert c.is_supported() is False
    c.start()  # noop
    c.set_active(True)  # noop
    c.notify("title", "body")  # noop
    c.stop()  # noop


def test_build_icon_image_idle_and_active():
    pytest.importorskip("PIL")
    from app.widgets import tray
    idle = tray._build_icon_image(active=False)
    active = tray._build_icon_image(active=True)
    assert idle.size == (64, 64)
    assert active.size == (64, 64)
    # The two images shouldn't be identical (different pixels).
    assert list(idle.getdata()) != list(active.getdata())
