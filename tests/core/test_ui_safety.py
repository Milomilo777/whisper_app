"""Tests for the UI safety fixes (P1-12/13/19).

We can't easily spin a real Tk root in CI, so these tests poke at
the underlying helpers + use stubbed Tk objects where the path
under test is logic-only.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from core import hub as _hub


# ---------------------------------------------------------------- P1-12

def test_install_excepthook_routes_tk_callbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Installing the excepthook also wires Tk.report_callback_exception."""
    import tkinter as tk

    from app.dialogs.crash import install_excepthook

    captured: list[Any] = []

    def fake_get_root() -> None:
        return None

    # Stub CrashDialog so we don't open a real window.
    import app.dialogs.crash as _crash

    class _FakeDialog:
        def __init__(self, *a: Any, **kw: Any) -> None:
            captured.append(("dialog", a, kw))

    monkeypatch.setattr(_crash, "CrashDialog", _FakeDialog)

    install_excepthook(get_root=fake_get_root)

    # Verify both ``tk.Tk`` and ``tk.Misc`` got the hook patched.
    # They should be the same function (our wrapper).
    assert tk.Tk.report_callback_exception is tk.Misc.report_callback_exception
    # And invoking it once should route through to CrashDialog.

    # Build a tiny synthetic call: the hook signature on Tk is
    # ``(self, exc, val, tb)``. We don't construct a real Tk widget;
    # any object will do because the hook ignores ``self``.
    fake_widget = object()
    try:
        raise ValueError("test crash")
    except ValueError:
        exc_type, exc_value, tb = sys.exc_info()
    tk.Tk.report_callback_exception(  # type: ignore[arg-type]
        fake_widget, exc_type, exc_value, tb,  # type: ignore[arg-type]
    )
    assert any(c[0] == "dialog" for c in captured), (
        "Tk callback hook did not invoke CrashDialog"
    )


# ---------------------------------------------------------------- P1-13

def test_stop_worker_tolerates_closed_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker that already closed its stdin must not crash _stop_worker."""
    from app.app import App

    class _FakeStdin:
        def write(self, data: str) -> int:
            raise OSError("Broken pipe")

        def flush(self) -> None:
            raise OSError("Broken pipe")

        def close(self) -> None:
            pass

    class _FakeProc:
        stdin = _FakeStdin()

        def __init__(self) -> None:
            self._polled = False

        def poll(self) -> int | None:
            # First call returns None (alive), then 0 (exited).
            if not self._polled:
                self._polled = True
                return None
            return 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    class _Stub:
        def __init__(self) -> None:
            self.worker: dict[str, Any] | None = {
                "process": _FakeProc(),
                "ready": True,
                "task": None,
                "token": "t",
            }

    stub = _Stub()
    stop = App._stop_worker.__get__(stub, _Stub)

    # Must not raise even though stdin.write throws.
    stop()
    assert stub.worker is None


# ---------------------------------------------------------------- P1-19

def test_validate_hub_path_rejects_system_dirs() -> None:
    if os.name == "nt":
        ok, reason = _hub.validate_hub_path(r"C:\Windows\System32")
        assert not ok
        assert "system" in reason.lower()
        ok, reason = _hub.validate_hub_path(r"C:\Program Files\foo")
        assert not ok
        ok, reason = _hub.validate_hub_path(r"C:\Windows")
        assert not ok
    else:
        ok, reason = _hub.validate_hub_path("/etc/something")
        assert not ok
        ok, reason = _hub.validate_hub_path("/usr/lib/x")
        assert not ok


def test_validate_hub_path_rejects_drive_root() -> None:
    if os.name != "nt":
        pytest.skip("drive-root rule is Windows-only")
    ok, reason = _hub.validate_hub_path(r"C:\\")
    assert not ok
    assert "drive root" in reason.lower()


def test_validate_hub_path_rejects_empty() -> None:
    ok, reason = _hub.validate_hub_path("")
    assert not ok
    assert reason


def test_validate_hub_path_accepts_user_folder(tmp_path: Path) -> None:
    # Use the test's tmp_path — sits under TEMP, which is the user's
    # profile dir on Windows and ``/tmp`` on POSIX; both are
    # acceptable hub locations.
    ok, reason = _hub.validate_hub_path(str(tmp_path / "hub"))
    assert ok, reason
