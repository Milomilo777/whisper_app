"""Parity test for the Pascal-Script hub_folder parser in installer.iss.

The uninstaller's Pascal Script reads config.json line-by-line to
extract the user's ``hub_folder`` choice and decide whether to
prompt about deleting it. We can't run Inno Setup from CI, so this
test mirrors the parser in Python and verifies it stays in sync
with the JSON shape ``core.config.save_config`` actually emits.

If you change either the Pascal Script in installer.iss or the
JSON layout in core/config.py, this test catches the drift before
the user hits a broken uninstall.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.config import save_config


# --- Python mirror of the Pascal Script ---------------------------------------


def _parse_hub_folder_from_config_file(config_path: Path) -> str:
    """Mirror of ExtractHubFolder() in installer.iss [Code].

    Walks the file line-by-line, finds the first line starting with
    ``"hub_folder"``, extracts the quoted value, un-escapes the JSON
    backslash pairs. Returns '' when the key is absent.
    """
    if not config_path.exists():
        return ""
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    for raw in lines:
        line = raw.strip()
        if not line.startswith('"hub_folder"'):
            continue
        colon = line.find(":")
        if colon < 0:
            continue
        value = line[colon + 1:].strip()
        start_q = value.find('"')
        if start_q < 0:
            continue
        end_q = value.find('"', start_q + 1)
        if end_q < 0:
            continue
        return value[start_q + 1:end_q].replace("\\\\", "\\")
    return ""


def _is_path_inside(child: str, parent: str) -> bool:
    """Mirror of IsPathInside() — case-insensitive prefix match with
    trailing-backslash normalisation."""
    if not child or not parent:
        return False

    def _norm(p: str) -> str:
        s = p.rstrip("\\/")
        return (s + "\\").lower()

    return _norm(child).startswith(_norm(parent))


# --- tests --------------------------------------------------------------------


def test_parser_extracts_hub_folder_from_saved_config(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.user_config_dir", lambda: tmp_path)
    cfg = {"hub_folder": r"D:\models\hub", "model_path": ""}
    save_config(cfg)
    out = _parse_hub_folder_from_config_file(tmp_path / "config.json")
    assert out == r"D:\models\hub"


def test_parser_returns_empty_for_missing_file(tmp_path):
    assert _parse_hub_folder_from_config_file(tmp_path / "no.json") == ""


def test_parser_returns_empty_when_hub_folder_blank(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.user_config_dir", lambda: tmp_path)
    save_config({"hub_folder": "", "model_path": ""})
    assert _parse_hub_folder_from_config_file(tmp_path / "config.json") == ""


def test_parser_handles_paths_with_backslashes(tmp_path, monkeypatch):
    """JSON escapes \\ as \\\\; the parser must un-escape back."""
    monkeypatch.setattr("core.config.user_config_dir", lambda: tmp_path)
    nested = r"C:\Program Files\WhisperProject\hub"
    save_config({"hub_folder": nested})
    out = _parse_hub_folder_from_config_file(tmp_path / "config.json")
    assert out == nested


def test_parser_handles_paths_with_forward_slashes(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.user_config_dir", lambda: tmp_path)
    save_config({"hub_folder": "/srv/whisper/hub"})
    out = _parse_hub_folder_from_config_file(tmp_path / "config.json")
    assert out == "/srv/whisper/hub"


def test_parser_handles_unicode_path(tmp_path, monkeypatch):
    """JSON serialises non-ASCII paths via ensure_ascii=False (per
    save_config) so the parser must read UTF-8 cleanly."""
    monkeypatch.setattr("core.config.user_config_dir", lambda: tmp_path)
    custom = r"C:\Users\Owner\Documents\données\hub"
    save_config({"hub_folder": custom})
    out = _parse_hub_folder_from_config_file(tmp_path / "config.json")
    assert out == custom


# --- is_path_inside parity ----------------------------------------------------


def test_is_path_inside_true_for_subdir():
    assert _is_path_inside(r"C:\App\hub", r"C:\App") is True


def test_is_path_inside_true_for_identical():
    # Same path with/without trailing slash.
    assert _is_path_inside(r"C:\App", r"C:\App\\") is True


def test_is_path_inside_case_insensitive():
    assert _is_path_inside(r"c:\app\hub", r"C:\App") is True


def test_is_path_inside_false_for_unrelated():
    assert _is_path_inside(r"D:\models", r"C:\App") is False


def test_is_path_inside_false_for_prefix_match_without_separator():
    """A path 'C:\\AppData\\foo' must NOT match parent 'C:\\App' —
    the trailing-backslash normalisation prevents that false hit."""
    assert _is_path_inside(r"C:\AppData\foo", r"C:\App") is False


def test_is_path_inside_false_for_empty_inputs():
    assert _is_path_inside("", r"C:\App") is False
    assert _is_path_inside(r"C:\App", "") is False


# --- iss file sanity ----------------------------------------------------------


def test_both_iss_files_contain_uninstall_code_section():
    repo_root = Path(__file__).resolve().parents[2]
    for name in ("installer.iss", "installer_embed.iss"):
        text = (repo_root / name).read_text(encoding="utf-8")
        assert "[Code]" in text, f"{name} missing [Code] section"
        assert "CurUninstallStepChanged" in text, (
            f"{name} missing uninstall hook"
        )
        assert "hub_folder" in text, f"{name} doesn't reference hub_folder"
        assert "localappdata" in text, (
            f"{name} reads from wrong AppData root"
        )


def test_pascal_function_signatures_match_inno_conventions():
    """Spot-check the Pascal Script declares the events Inno expects."""
    repo_root = Path(__file__).resolve().parents[2]
    for name in ("installer.iss", "installer_embed.iss"):
        text = (repo_root / name).read_text(encoding="utf-8")
        # Inno requires this exact signature for uninstall hooks:
        assert re.search(
            r"procedure\s+CurUninstallStepChanged\(\s*CurUninstallStep\s*:\s*TUninstallStep\s*\)",
            text,
        ), f"{name} has wrong CurUninstallStepChanged signature"
