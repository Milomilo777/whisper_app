"""Tests for the first-run Hub Folder dialog."""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")


from app.dialogs.hub_setup import HubSetupDialog, ensure_hub_configured
from core import hub


# ---------- ensure_hub_configured short-circuit -------------------------------


def test_ensure_hub_configured_returns_existing_path_without_dialog():
    """When the config already has a hub_folder, no dialog should
    be constructed and the existing path is returned verbatim."""
    cfg = {"hub_folder": "/some/path"}
    root = tk.Tk()
    root.withdraw()
    try:
        # Use a save that fails loudly if invoked — proves no dialog
        # construction happened.
        def _fail_save(_c):
            raise AssertionError("save should not be called on the no-op path")

        out = ensure_hub_configured(root, cfg, save=_fail_save)
        assert out == "/some/path"
    finally:
        root.destroy()


def test_ensure_hub_configured_returns_default_when_unset_and_opens_dialog(tmp_path, monkeypatch):
    """When hub_folder is missing, the helper returns the default
    string for the session AND opens a dialog Toplevel."""
    monkeypatch.setattr(hub, "resolve_app_dir", lambda: tmp_path)
    cfg = {}
    root = tk.Tk()
    root.withdraw()
    try:
        out = ensure_hub_configured(root, cfg, save=lambda _c: None)
        assert out == str(tmp_path / hub.HUB_SUBFOLDER_NAME)
        # A Toplevel child got created.
        children = root.winfo_children()
        assert any(isinstance(c, HubSetupDialog) for c in children)
    finally:
        root.destroy()


# ---------- dialog OK persists + closes ---------------------------------------


def test_dialog_ok_writes_hub_folder_and_invokes_save(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "resolve_app_dir", lambda: tmp_path)
    cfg = {}
    saved_payloads: list[dict] = []
    root = tk.Tk()
    root.withdraw()
    try:
        dlg = HubSetupDialog(root, cfg, save=saved_payloads.append)
        # Type a custom path into the entry.
        custom = str(tmp_path / "my_custom_hub")
        dlg._path_var.set(custom)
        dlg._on_ok()
        assert cfg["hub_folder"] == custom
        assert dlg.chosen_path == custom
        assert dlg.saved is True
        assert len(saved_payloads) == 1
        assert saved_payloads[0]["hub_folder"] == custom
    finally:
        root.destroy()


def test_dialog_use_default_resets_entry_and_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "resolve_app_dir", lambda: tmp_path)
    cfg = {"hub_folder": ""}
    saved_payloads: list[dict] = []
    root = tk.Tk()
    root.withdraw()
    try:
        dlg = HubSetupDialog(root, cfg, save=saved_payloads.append)
        # User edited the path to nonsense; "Use default" should
        # reset before saving.
        dlg._path_var.set("/garbage")
        dlg._on_use_default()
        expected = str(tmp_path / hub.HUB_SUBFOLDER_NAME)
        assert cfg["hub_folder"] == expected
        assert dlg.chosen_path == expected
        assert dlg.saved is True
    finally:
        root.destroy()


def test_dialog_cancel_does_not_save(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "resolve_app_dir", lambda: tmp_path)
    cfg = {"hub_folder": ""}
    saved_payloads: list[dict] = []
    root = tk.Tk()
    root.withdraw()
    try:
        dlg = HubSetupDialog(root, cfg, save=saved_payloads.append)
        dlg._path_var.set("/some/typed/path")
        dlg._on_cancel()
        # Cancel returns the default but does NOT mutate config.
        assert cfg["hub_folder"] == ""
        assert saved_payloads == []
        assert dlg.saved is False
        # Caller still gets a usable path for the session.
        assert dlg.chosen_path == str(tmp_path / hub.HUB_SUBFOLDER_NAME)
    finally:
        root.destroy()


# ---------- on_done callback --------------------------------------------------


def test_on_done_callback_receives_saved_path(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "resolve_app_dir", lambda: tmp_path)
    cfg = {"hub_folder": ""}
    received: list[str] = []
    root = tk.Tk()
    root.withdraw()
    try:
        dlg = HubSetupDialog(
            root, cfg,
            save=lambda _c: None,
            on_done=received.append,
        )
        custom = str(tmp_path / "external")
        dlg._path_var.set(custom)
        dlg._on_ok()
        assert received == [custom]
    finally:
        root.destroy()


def test_on_done_callback_swallows_exceptions(tmp_path, monkeypatch):
    """A broken on_done callback must not crash the dialog flow —
    the user has already committed; subsequent failures are logged
    but the dialog must still close cleanly."""
    monkeypatch.setattr(hub, "resolve_app_dir", lambda: tmp_path)
    cfg = {"hub_folder": ""}

    def _boom(_p):
        raise RuntimeError("callback boom")

    root = tk.Tk()
    root.withdraw()
    try:
        dlg = HubSetupDialog(
            root, cfg,
            save=lambda _c: None,
            on_done=_boom,
        )
        dlg._on_use_default()
        # No exception escaped; dialog destroyed itself.
        assert not dlg.winfo_exists()
    finally:
        root.destroy()


# ---------- save_callback failure tolerance -----------------------------------


def test_dialog_save_failure_still_closes_cleanly(tmp_path, monkeypatch):
    """A save failure (disk-full, permissions) must not leave the
    dialog open. saved must read False so the caller can retry."""
    monkeypatch.setattr(hub, "resolve_app_dir", lambda: tmp_path)

    def _broken_save(_c):
        raise OSError("disk full")

    cfg = {"hub_folder": ""}
    root = tk.Tk()
    root.withdraw()
    try:
        dlg = HubSetupDialog(root, cfg, save=_broken_save)
        dlg._on_ok()
        # cfg was still mutated in-memory (the OK semantics).
        assert cfg["hub_folder"]
        assert dlg.saved is False
        assert not dlg.winfo_exists()
    finally:
        root.destroy()
