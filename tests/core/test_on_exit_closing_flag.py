"""Regression test for App.on_exit and the _closing freeze (HIGH-1).

on_exit used to set ``self._closing = True`` BEFORE the "Exit with queued
tasks?" confirmation and ``return`` on "No" without resetting it. ``_closing``
is only reset in __init__, and it is the sole gate that lets ``loop()``
(self.after(500, self.loop)), ``_drain_main_calls`` and
``_drain_watched_paths`` re-arm their after() callbacks. So declining the
exit dialog permanently froze the app: the queue pump, the post-to-main
drain and the watched-folder drain all died.

These tests run App.on_exit against a SimpleNamespace fake "self" (no real
Tk root, per the project's Tk-free-tests rule), monkeypatching the
module-level ``messagebox`` so the dialog never renders.
"""
from __future__ import annotations

import types
from typing import Any

import pytest


def _fake_task(status: str = "running") -> types.SimpleNamespace:
    return types.SimpleNamespace(status=status, process=None)


def _fake_self(queue, download_queue) -> types.SimpleNamespace:
    """Minimal self carrying only what the decline path of on_exit reads."""
    return types.SimpleNamespace(
        _exit_from_tray=True,        # skip the minimise-to-tray redirect
        app_config={},
        tray=None,
        queue=queue,
        download_queue=download_queue,
        _closing=False,
    )


def test_on_exit_decline_does_not_set_closing(monkeypatch: Any) -> None:
    """Declining the exit dialog must leave _closing False (no freeze)."""
    from app import app as app_module

    monkeypatch.setattr(app_module.messagebox, "askyesno",
                        lambda *_a, **_k: False)

    fake = _fake_self(queue=[_fake_task("running")], download_queue=[])
    app_module.App.on_exit(fake)  # type: ignore[arg-type]

    assert fake._closing is False, (
        "on_exit must NOT leave _closing True after the user declines — that "
        "permanently freezes loop()/_drain_main_calls/_drain_watched_paths."
    )


def test_on_exit_decline_with_active_download(monkeypatch: Any) -> None:
    """Same guarantee when only a download is active."""
    from app import app as app_module

    monkeypatch.setattr(app_module.messagebox, "askyesno",
                        lambda *_a, **_k: False)

    fake = _fake_self(queue=[], download_queue=[_fake_task("running")])
    app_module.App.on_exit(fake)  # type: ignore[arg-type]

    assert fake._closing is False


def test_on_exit_no_active_tasks_does_not_prompt(monkeypatch: Any) -> None:
    """With nothing active, on_exit proceeds and sets _closing without a dialog.

    We stop the teardown right after the flag flip by making the next call it
    makes (_save_window_geometry) raise a sentinel we catch — proving the flag
    was set on the proceed path and the dialog was never shown.
    """
    from app import app as app_module

    def _boom(*_a, **_k):
        raise RuntimeError("STOP")

    called = {"asked": False}

    def _ask(*_a, **_k):
        called["asked"] = True
        return True

    monkeypatch.setattr(app_module.messagebox, "askyesno", _ask)

    fake = _fake_self(queue=[_fake_task("finished")],
                      download_queue=[_fake_task("cancelled")])
    fake._save_window_geometry = _boom

    with pytest.raises(RuntimeError, match="STOP"):
        app_module.App.on_exit(fake)  # type: ignore[arg-type]

    assert called["asked"] is False  # no active tasks -> no confirmation
    assert fake._closing is True     # proceed path set the flag


def test_on_exit_confirm_sets_closing(monkeypatch: Any) -> None:
    """Confirming exit with active tasks sets _closing (then proceeds)."""
    from app import app as app_module

    monkeypatch.setattr(app_module.messagebox, "askyesno",
                        lambda *_a, **_k: True)

    def _boom(*_a, **_k):
        raise RuntimeError("STOP")

    fake = _fake_self(queue=[_fake_task("running")], download_queue=[])
    fake._save_window_geometry = _boom

    with pytest.raises(RuntimeError, match="STOP"):
        app_module.App.on_exit(fake)  # type: ignore[arg-type]

    assert fake._closing is True
