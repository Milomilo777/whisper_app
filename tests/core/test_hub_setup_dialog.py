"""Tests for the first-run Hub Folder dialog."""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")


from app.dialogs.hub_setup import HubSetupDialog, ensure_hub_configured
from core import hub


@pytest.fixture
def tk_root():
    """Yield a hidden Tk root that is destroyed at fixture teardown.

    Creating a fresh ``tk.Tk()`` per test was causing intermittent
    Tcl-state corruption when run with many sibling Tk-using tests
    (transcript_viewer, hardware_wizard, etc.). Sharing a root
    per-test via a fixture lets us reliably clean it up + keeps the
    test units independent.
    """
    root = tk.Tk()
    root.withdraw()
    try:
        yield root
    finally:
        try:
            root.update_idletasks()
        except tk.TclError:
            pass
        try:
            root.destroy()
        except tk.TclError:
            pass


# ---------- ensure_hub_configured short-circuit -------------------------------


def test_ensure_hub_configured_returns_existing_path_without_dialog():
    """When the config already has a hub_folder, no dialog should
    be constructed and the existing path is returned verbatim.

    Note: we deliberately use a mock master here instead of a real
    ``tk.Tk()`` root because this code path early-returns before
    touching the master. Real Tk roots in a test suite that runs
    many Tk-heavy tests (transcript_viewer, hardware_wizard,
    hub_setup_dialog construction, …) sometimes accumulate state
    that surfaces as a flaky failure on this lone test. The mock
    keeps the unit pure.
    """
    from unittest.mock import MagicMock

    cfg = {"hub_folder": "/some/path"}
    fake_master = MagicMock()

    # Use a save that fails loudly if invoked — proves no dialog
    # construction happened.
    def _fail_save(_c):
        raise AssertionError("save should not be called on the no-op path")

    out = ensure_hub_configured(fake_master, cfg, save=_fail_save)
    assert out == "/some/path"
    # The master must NOT have been used for any Tk operation
    # (no HubSetupDialog constructed → no method calls on master).
    assert not fake_master.method_calls, (
        f"master should not be touched on the no-op path, got "
        f"{fake_master.method_calls}"
    )


def test_ensure_hub_configured_returns_default_when_unset_and_opens_dialog(tmp_path, monkeypatch):
    """When hub_folder is missing, the helper returns the default
    string for the session AND constructs a HubSetupDialog.

    We mock the dialog class so we can assert it was called with
    the right args WITHOUT racing other Tk-heavy tests in the
    suite (same flake-mitigation pattern as the no-dialog test).
    """
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(hub, "default_hub_folder", lambda: tmp_path / hub.HUB_SUBFOLDER_NAME)
    cfg = {}
    fake_master = MagicMock()
    fake_save = MagicMock()
    fake_on_done = MagicMock()

    with patch("app.dialogs.hub_setup.HubSetupDialog") as MockDialog:
        out = ensure_hub_configured(
            fake_master, cfg, save=fake_save, on_done=fake_on_done,
        )
        # Returns the platform-default string for the session.
        assert out == str(tmp_path / hub.HUB_SUBFOLDER_NAME)
        # Dialog was constructed exactly once with the right args.
        MockDialog.assert_called_once_with(
            fake_master, cfg, save=fake_save, on_done=fake_on_done,
        )


# ---------- dialog OK persists + closes ---------------------------------------


def test_dialog_ok_writes_hub_folder_and_invokes_save(tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "default_hub_folder", lambda: tmp_path / hub.HUB_SUBFOLDER_NAME)
    cfg = {}
    saved_payloads: list[dict] = []
    dlg = HubSetupDialog(tk_root, cfg, save=saved_payloads.append)
    # Type a custom path into the entry.
    custom = str(tmp_path / "my_custom_hub")
    dlg._path_var.set(custom)
    dlg._on_ok()
    assert cfg["hub_folder"] == custom
    assert dlg.chosen_path == custom
    assert dlg.saved is True
    assert len(saved_payloads) == 1
    assert saved_payloads[0]["hub_folder"] == custom


def test_dialog_use_default_resets_entry_and_saves(tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "default_hub_folder", lambda: tmp_path / hub.HUB_SUBFOLDER_NAME)
    cfg = {"hub_folder": ""}
    saved_payloads: list[dict] = []
    dlg = HubSetupDialog(tk_root, cfg, save=saved_payloads.append)
    # User edited the path to nonsense; "Use default" should
    # reset before saving.
    dlg._path_var.set("/garbage")
    dlg._on_use_default()
    expected = str(tmp_path / hub.HUB_SUBFOLDER_NAME)
    assert cfg["hub_folder"] == expected
    assert dlg.chosen_path == expected
    assert dlg.saved is True


def test_dialog_cancel_does_not_save(tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "default_hub_folder", lambda: tmp_path / hub.HUB_SUBFOLDER_NAME)
    cfg = {"hub_folder": ""}
    saved_payloads: list[dict] = []
    dlg = HubSetupDialog(tk_root, cfg, save=saved_payloads.append)
    dlg._path_var.set("/some/typed/path")
    dlg._on_cancel()
    # Cancel returns the default but does NOT mutate config.
    assert cfg["hub_folder"] == ""
    assert saved_payloads == []
    assert dlg.saved is False
    # Caller still gets a usable path for the session.
    assert dlg.chosen_path == str(tmp_path / hub.HUB_SUBFOLDER_NAME)


# ---------- on_done callback --------------------------------------------------


def test_on_done_callback_receives_saved_path(tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "default_hub_folder", lambda: tmp_path / hub.HUB_SUBFOLDER_NAME)
    cfg = {"hub_folder": ""}
    received: list[str] = []
    dlg = HubSetupDialog(
        tk_root, cfg,
        save=lambda _c: None,
        on_done=received.append,
    )
    custom = str(tmp_path / "external")
    dlg._path_var.set(custom)
    dlg._on_ok()
    assert received == [custom]


def test_on_done_callback_swallows_exceptions(tk_root, tmp_path, monkeypatch):
    """A broken on_done callback must not crash the dialog flow —
    the user has already committed; subsequent failures are logged
    but the dialog must still close cleanly."""
    monkeypatch.setattr(hub, "default_hub_folder", lambda: tmp_path / hub.HUB_SUBFOLDER_NAME)
    cfg = {"hub_folder": ""}

    def _boom(_p):
        raise RuntimeError("callback boom")

    dlg = HubSetupDialog(
        tk_root, cfg,
        save=lambda _c: None,
        on_done=_boom,
    )
    dlg._on_use_default()
    # No exception escaped; dialog destroyed itself.
    assert not dlg.winfo_exists()


# ---------- save_callback failure tolerance -----------------------------------


def test_dialog_save_failure_still_closes_cleanly(tk_root, tmp_path, monkeypatch):
    """A save failure (disk-full, permissions) must not leave the
    dialog open. saved must read False so the caller can retry."""
    monkeypatch.setattr(hub, "default_hub_folder", lambda: tmp_path / hub.HUB_SUBFOLDER_NAME)

    def _broken_save(_c):
        raise OSError("disk full")

    cfg = {"hub_folder": ""}
    dlg = HubSetupDialog(tk_root, cfg, save=_broken_save)
    dlg._on_ok()
    # cfg was still mutated in-memory (the OK semantics).
    assert cfg["hub_folder"]
    assert dlg.saved is False
    assert not dlg.winfo_exists()
