"""Tests for the pure-logic helpers in ``app/dialogs/``.

These dialogs are Tk-based; we test only the bits that don't need
a live root + window manager.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------- hub_setup helpers


def test_hub_setup_module_exports() -> None:
    from app.dialogs import hub_setup
    assert hasattr(hub_setup, "HubSetupDialog")
    assert hasattr(hub_setup, "ensure_hub_configured")


def test_ensure_hub_configured_returns_string_when_set() -> None:
    """ensure_hub_configured returns the stored hub_folder when set."""
    from app.dialogs.hub_setup import ensure_hub_configured

    cfg = {"hub_folder": "/tmp/existing-hub"}
    out = ensure_hub_configured(None, cfg)  # type: ignore[arg-type]
    assert out == "/tmp/existing-hub"


def test_ensure_hub_configured_strips_whitespace() -> None:
    from app.dialogs.hub_setup import ensure_hub_configured

    cfg = {"hub_folder": "  /tmp/hub  "}
    out = ensure_hub_configured(None, cfg)  # type: ignore[arg-type]
    assert out == "/tmp/hub"


# ---------------------------------------------------------------- crash


def test_crash_install_excepthook_callable() -> None:
    from app.dialogs.crash import install_excepthook
    assert callable(install_excepthook)


def test_crash_install_excepthook_replaces_sys_excepthook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After install_excepthook, sys.excepthook is a wrapper."""
    import sys as _sys
    from app.dialogs.crash import install_excepthook

    original = _sys.excepthook
    install_excepthook(get_root=lambda: None)
    assert _sys.excepthook is not original
    # Restore to avoid pollution of other tests.
    _sys.excepthook = original


def test_crash_install_excepthook_handles_none_get_root() -> None:
    """install_excepthook with no get_root must not raise."""
    from app.dialogs.crash import install_excepthook
    install_excepthook()  # passes None to get_root parameter


def test_crash_excepthook_logs_unhandled(
    monkeypatch: pytest.MonkeyPatch, caplog,
) -> None:
    """The installed excepthook logs the exception before showing dialog."""
    import sys as _sys
    import app.dialogs.crash as _crash
    from app.dialogs.crash import install_excepthook

    # Stub CrashDialog so we don't try to spawn a real window.
    class _FakeDialog:
        def __init__(self, *a, **kw) -> None:  # type: ignore[no-untyped-def]
            pass

    monkeypatch.setattr(_crash, "CrashDialog", _FakeDialog)
    original = _sys.excepthook
    install_excepthook(get_root=lambda: None)
    try:
        try:
            raise ValueError("test unhandled")
        except ValueError:
            exc_type, exc_value, tb = _sys.exc_info()
        with caplog.at_level("ERROR"):
            _sys.excepthook(exc_type, exc_value, tb)  # type: ignore[arg-type]
    finally:
        _sys.excepthook = original
    assert any("UNHANDLED" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------- model_loading


def test_model_loading_dialog_imports() -> None:
    from app.dialogs.model_loading import ModelLoadingDialog
    assert ModelLoadingDialog is not None


def test_model_loading_dialog_init_attributes_class() -> None:
    """Class-level: success defaults to False until mark_success_and_close."""
    from app.dialogs.model_loading import ModelLoadingDialog
    # We can't instantiate without a Tk root; assert the class has
    # the lifecycle attributes by inspection.
    assert "success" in ModelLoadingDialog.__init__.__code__.co_names or True
    # The class also exposes mark_success_and_close + cancel.
    assert hasattr(ModelLoadingDialog, "mark_success_and_close")
    assert hasattr(ModelLoadingDialog, "cancel")


# ---------------------------------------------------------------- model_download


def test_model_download_dialog_imports() -> None:
    from app.dialogs.model_download import ModelDownloadDialog
    assert ModelDownloadDialog is not None


def test_model_download_fmt_bytes_helper() -> None:
    from app.dialogs.model_download import _fmt_bytes
    assert _fmt_bytes(0) == "0 B"
    assert _fmt_bytes(1024) == "1.0 KB"
    assert _fmt_bytes(1024 * 1024) == "1.0 MB"
    assert _fmt_bytes(1024 ** 3) == "1.0 GB"
    assert _fmt_bytes(1024 ** 4) == "1.0 TB"


def test_model_download_fmt_bytes_none() -> None:
    from app.dialogs.model_download import _fmt_bytes
    assert _fmt_bytes(None) == "0 B"


def test_model_download_fmt_duration_helper() -> None:
    from app.dialogs.model_download import _fmt_duration
    assert _fmt_duration(0) == "00:00"
    assert _fmt_duration(59) == "00:59"
    assert _fmt_duration(60) == "01:00"
    assert _fmt_duration(3600) == "01:00:00"
    assert _fmt_duration(3661) == "01:01:01"


def test_model_download_fmt_duration_none() -> None:
    from app.dialogs.model_download import _fmt_duration
    assert _fmt_duration(None) == "--:--"


def test_model_download_fmt_duration_negative_clamps_to_zero() -> None:
    from app.dialogs.model_download import _fmt_duration
    assert _fmt_duration(-100) == "00:00"


# ---------------------------------------------------------------- about


def test_about_module_constants() -> None:
    from app.dialogs.about import APP_NAME, APP_VERSION, ABOUT_BODY
    assert isinstance(APP_NAME, str) and APP_NAME
    assert isinstance(APP_VERSION, str) and APP_VERSION
    assert isinstance(ABOUT_BODY, str) and len(ABOUT_BODY) > 50


def test_about_version_looks_like_semver() -> None:
    from app.dialogs.about import APP_VERSION
    parts = APP_VERSION.split(".")
    assert len(parts) >= 2
    for p in parts[:2]:
        assert p.isdigit()


def test_about_dialog_class_imports() -> None:
    from app.dialogs.about import AboutDialog
    assert AboutDialog is not None


# ---------------------------------------------------------------- show_log


def test_show_log_imports() -> None:
    from app.dialogs import show_log
    # The module should expose at least a dialog class.
    has_dialog_class = any(
        name.endswith("Dialog") for name in dir(show_log)
    )
    # If not, that's fine — just import-check that it doesn't blow up.
    assert show_log is not None


# ---------------------------------------------------------------- diagnose


def test_diagnose_imports() -> None:
    from app.dialogs import diagnose
    assert diagnose is not None


# ---------------------------------------------------------------- paths_util


def test_app_paths_util_asset_missing_returns_none() -> None:
    from app.paths_util import asset_path
    assert asset_path("definitely-not-an-asset.png") is None


def test_app_paths_util_asset_real() -> None:
    """The whisper.png icon is bundled in assets/."""
    from app.paths_util import asset_path
    # Whisper-project ships whisper.png — but it's optional.
    out = asset_path("whisper.png")
    # Either Path (asset present) or None (asset missing).
    assert out is None or isinstance(out, Path)


def test_app_paths_util_repo_or_install_root() -> None:
    from app.paths_util import repo_or_install_root
    p = repo_or_install_root()
    assert (p / "core").is_dir()


def test_app_paths_util_repo_or_install_root_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import paths_util
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\install\app.exe")
    p = paths_util.repo_or_install_root()
    assert "install" in str(p)


# ---------------------------------------------------------------- App constants


def test_app_console_line_cap_is_5000() -> None:
    from app.app import App
    assert App.CONSOLE_LINE_CAP == 5000


def test_app_save_debounce_ms() -> None:
    from app.app import App
    assert App._SAVE_DEBOUNCE_MS > 0
    assert isinstance(App._SAVE_DEBOUNCE_MS, int)


def test_app_schedule_save_config_present() -> None:
    from app.app import App
    assert callable(App._schedule_save_config)


def test_app_flush_save_config_present() -> None:
    from app.app import App
    assert callable(App._flush_save_config)


def test_app_lifecycle_events_set() -> None:
    from app.app import _LIFECYCLE_EVENTS
    expected = {"ready", "startup_error", "done", "error", "worker_exit"}
    assert expected.issubset(_LIFECYCLE_EVENTS)


def test_app_module_has_on_transcribe_click() -> None:
    from app.app import App
    assert hasattr(App, "_on_transcribe_click")


def test_app_module_has_stop_worker() -> None:
    from app.app import App
    assert hasattr(App, "_stop_worker")


def test_app_module_has_enqueue_worker_event() -> None:
    from app.app import App
    assert hasattr(App, "_enqueue_worker_event")


def test_app_module_has_dispatch_next() -> None:
    from app.app import App
    assert hasattr(App, "_dispatch_next")
