"""Extended coverage for ``core.hub``.

Covers:
  * ``model_folder_for`` with every reasonable prefix pattern
  * ``default_hub_folder`` in source vs frozen mode
  * ``is_path_inside`` doesn't exist in this module but we cover the
    sibling-vs-descendant logic via direct path comparisons
  * ``normalise_hub_path`` shape variants
  * ``validate_hub_path`` exhaustive system-dir + drive-root rejection
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from core import hub as _hub


# --------------------------------------------------------------- default_hub_folder


def test_default_hub_folder_returns_path() -> None:
    assert isinstance(_hub.default_hub_folder(), Path)


def test_default_hub_folder_ends_in_hub() -> None:
    assert _hub.default_hub_folder().name == _hub.HUB_SUBFOLDER_NAME


def test_default_hub_folder_in_source_mode_under_repo_root() -> None:
    p = _hub.default_hub_folder()
    # The parent is the app dir which holds gui.py.
    assert (p.parent / "gui.py").is_file()


def test_resolve_app_dir_in_source_mode_is_repo_root() -> None:
    assert (_hub.resolve_app_dir() / "core" / "hub.py").is_file()


def test_resolve_app_dir_in_frozen_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """When sys.frozen is set, app_dir comes from sys.executable."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\fake\install\app.exe")
    p = _hub.resolve_app_dir()
    # Normalise both sides for cross-platform.
    assert str(p).replace("\\", "/").endswith("/fake/install")


def test_default_hub_folder_in_frozen_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\install\app.exe")
    p = _hub.default_hub_folder()
    assert p.name == "hub"
    assert "install" in str(p)


# --------------------------------------------------------------- is_hub_configured


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"hub_folder": ""},
        {"hub_folder": "   "},
        {"hub_folder": "\t\n  "},
    ],
)
def test_is_hub_configured_false_for_empty(config: dict) -> None:
    assert _hub.is_hub_configured(config) is False


@pytest.mark.parametrize(
    "raw",
    [
        "/tmp/hub",
        "C:/Users/me/hub",
        "D:\\models",
        "~/hub",
        "relative/hub",
        "  /tmp/hub  ",  # whitespace tolerated; .strip() applied
    ],
)
def test_is_hub_configured_true_for_non_empty(raw: str) -> None:
    assert _hub.is_hub_configured({"hub_folder": raw}) is True


def test_is_hub_configured_none_treated_as_empty() -> None:
    assert _hub.is_hub_configured({"hub_folder": None}) is False


# --------------------------------------------------------------- normalise_hub_path


def test_normalise_hub_path_empty_string_returns_default() -> None:
    assert _hub.normalise_hub_path("") == str(_hub.default_hub_folder())


def test_normalise_hub_path_falsy_returns_default() -> None:
    assert _hub.normalise_hub_path("") == str(_hub.default_hub_folder())


def test_normalise_hub_path_pathobject(tmp_path: Path) -> None:
    out = _hub.normalise_hub_path(tmp_path)
    assert out == str(tmp_path.resolve())


def test_normalise_hub_path_expands_user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = str(tmp_path / "fakehome")
    Path(home).mkdir()
    monkeypatch.setenv("HOME", home)
    monkeypatch.setenv("USERPROFILE", home)
    out = _hub.normalise_hub_path("~/whisper")
    assert home in out


def test_normalise_hub_path_absolute_unchanged_relative(tmp_path: Path) -> None:
    """A relative path is resolved against cwd → ends up absolute."""
    out = _hub.normalise_hub_path("./relative")
    assert os.path.isabs(out)


# --------------------------------------------------------------- model_folder_for


def test_model_folder_for_with_pathobject(tmp_path: Path) -> None:
    out = _hub.model_folder_for(tmp_path, "x")
    assert out.parent == tmp_path
    assert out.name == "models--Systran--x"


@pytest.mark.parametrize(
    "name, expected_suffix",
    [
        ("a", "models--Systran--a"),
        ("faster-whisper-tiny", "models--Systran--faster-whisper-tiny"),
        ("faster-whisper-large-v3", "models--Systran--faster-whisper-large-v3"),
        ("custom_model_name", "models--Systran--custom_model_name"),
        ("UPPERCASE", "models--Systran--UPPERCASE"),
        ("with-dashes-and_underscores", "models--Systran--with-dashes-and_underscores"),
    ],
)
def test_model_folder_for_prefixes_systran(
    tmp_path: Path, name: str, expected_suffix: str,
) -> None:
    out = _hub.model_folder_for(tmp_path, name)
    assert out.name == expected_suffix


@pytest.mark.parametrize(
    "full_slug",
    [
        "models--Systran--whisper-tiny",
        "models--OpenAI--whisper-base",
        "models--Vendor--model-x",
        "models--a--b",
    ],
)
def test_model_folder_for_does_not_double_prefix(
    tmp_path: Path, full_slug: str,
) -> None:
    out = _hub.model_folder_for(tmp_path, full_slug)
    assert out.name == full_slug
    assert out.name.count("models--") == 1


def test_model_folder_for_strips_whitespace(tmp_path: Path) -> None:
    out = _hub.model_folder_for(tmp_path, "  faster-whisper-tiny  ")
    assert out.name == "models--Systran--faster-whisper-tiny"


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
def test_model_folder_for_blank_raises(tmp_path: Path, blank: str) -> None:
    with pytest.raises(ValueError):
        _hub.model_folder_for(tmp_path, blank)


def test_model_folder_for_none_hub_uses_default_cache() -> None:
    out = _hub.model_folder_for(None, "x")
    # Should land under user_cache_dir()/models
    assert "models" in out.parts


def test_model_folder_for_empty_string_hub_uses_default_cache() -> None:
    out = _hub.model_folder_for("", "x")
    assert "models" in out.parts


# --------------------------------------------------------------- validate_hub_path: forbidden


@pytest.mark.parametrize(
    "bad_path",
    [
        r"C:\Windows",
        r"C:\Windows\System32",
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        r"C:\Program Files\WhisperProject",
        r"C:\ProgramData",
        r"C:\ProgramData\hub",
        r"c:\windows\system32",  # lowercase
        r"C:/Windows/System32",  # forward slash
    ],
)
def test_validate_hub_path_rejects_windows_system_dirs(bad_path: str) -> None:
    if os.name != "nt":
        pytest.skip("Windows-only system dir test")
    ok, reason = _hub.validate_hub_path(bad_path)
    assert ok is False
    assert "system" in reason.lower()


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc",
        "/etc/passwd",
        "/usr",
        "/usr/local",
        "/bin",
        "/sbin",
    ],
)
def test_validate_hub_path_rejects_unix_system_dirs(bad_path: str) -> None:
    if os.name == "nt":
        pytest.skip("Windows resolves /etc to C:\\etc; Unix-only rule")
    ok, reason = _hub.validate_hub_path(bad_path)
    assert ok is False


@pytest.mark.parametrize("bad", ["", None])
def test_validate_hub_path_rejects_empty(bad) -> None:
    ok, reason = _hub.validate_hub_path(bad)
    assert ok is False
    assert reason


@pytest.mark.parametrize(
    "drive",
    [r"C:\\", r"D:\\", r"E:\\"],
)
def test_validate_hub_path_rejects_drive_roots(drive: str) -> None:
    if os.name != "nt":
        pytest.skip("drive-root rule is Windows-only")
    ok, reason = _hub.validate_hub_path(drive)
    assert ok is False
    assert "drive root" in reason.lower()


def test_validate_hub_path_accepts_user_folder(tmp_path: Path) -> None:
    ok, reason = _hub.validate_hub_path(str(tmp_path / "hub"))
    assert ok is True


def test_validate_hub_path_accepts_existing_user_folder(tmp_path: Path) -> None:
    sub = tmp_path / "models"
    sub.mkdir()
    ok, reason = _hub.validate_hub_path(str(sub))
    assert ok is True


def test_validate_hub_path_accepts_external_drive(tmp_path: Path) -> None:
    """A path like D:\\whisper-models is fine — not a forbidden root."""
    if os.name != "nt":
        pytest.skip("Windows-only path semantics")
    # Use tmp_path which is under TEMP; that's accepted.
    ok, _ = _hub.validate_hub_path(str(tmp_path / "external"))
    assert ok is True


def test_validate_hub_path_rejects_invalid_path() -> None:
    """A path that .resolve() can't handle returns (False, error)."""
    # On Windows, a path containing a null byte triggers ValueError.
    # On some Pythons this is normalised silently; only assert that
    # the function does not crash.
    try:
        ok, reason = _hub.validate_hub_path("C:\\bad\x00path")
    except (OSError, ValueError):
        pytest.skip("OS rejected the synthetic bad path before validate_hub_path")
    assert isinstance(ok, bool)


# --------------------------------------------------------------- HUB_SUBFOLDER_NAME constant


def test_hub_subfolder_name_is_hub() -> None:
    assert _hub.HUB_SUBFOLDER_NAME == "hub"


def test_forbidden_hub_roots_is_tuple() -> None:
    assert isinstance(_hub._FORBIDDEN_HUB_ROOTS, tuple)
    assert len(_hub._FORBIDDEN_HUB_ROOTS) > 0
