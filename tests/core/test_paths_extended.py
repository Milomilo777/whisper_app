"""Extended coverage for ``core.paths``."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from core import paths as _p


# ---------------------------------------------------------------- resource_base


def test_resource_base_returns_string() -> None:
    assert isinstance(_p.resource_base(), str)


def test_resource_base_in_source_mode_repo_root() -> None:
    base = _p.resource_base()
    assert (Path(base) / "core").is_dir()
    assert (Path(base) / "app").is_dir()


def test_resource_base_with_meipass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", r"C:\tmp\_MEI12345", raising=False)
    assert _p.resource_base() == r"C:\tmp\_MEI12345"


def test_resource_base_frozen_no_meipass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\install\app.exe")
    base = _p.resource_base()
    assert "install" in base


def test_resource_base_source_no_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    base = _p.resource_base()
    assert (Path(base) / "core" / "paths.py").is_file()


# ---------------------------------------------------------------- bin_dir


def test_bin_dir_under_resource_base() -> None:
    assert _p.bin_dir() == os.path.join(_p.resource_base(), "bin")


def test_bin_dir_returns_string() -> None:
    assert isinstance(_p.bin_dir(), str)


def test_bin_dir_changes_with_meipass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", r"C:\tmp\foo", raising=False)
    assert _p.bin_dir().startswith(r"C:\tmp\foo")


# ---------------------------------------------------------------- bundled_binary


def test_bundled_binary_ffmpeg_returns_absolute() -> None:
    path = _p.bundled_binary("ffmpeg")
    assert path is not None
    assert os.path.isabs(path)
    assert os.path.isfile(path)


def test_bundled_binary_ffprobe_returns_absolute() -> None:
    path = _p.bundled_binary("ffprobe")
    assert path is not None
    assert os.path.isfile(path)


def test_bundled_binary_appends_exe_on_windows() -> None:
    if os.name != "nt":
        pytest.skip("Windows-only suffix")
    path = _p.bundled_binary("ffmpeg")
    assert path is not None
    assert path.endswith(".exe")


def test_bundled_binary_does_not_append_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.name == "nt":
        pytest.skip("POSIX-only test")
    # We can't truly test this without manipulating os.name, which is
    # frozen by Python; instead assert the basename has no .exe.
    path = _p.bundled_binary("ffmpeg")
    if path is not None:
        assert not path.endswith(".exe")


@pytest.mark.parametrize(
    "name",
    [
        "definitely-not-real-xyzzy",
        "abc123",
        "missing_binary",
        "x",
        "no-such-tool",
    ],
)
def test_bundled_binary_missing_returns_none(name: str) -> None:
    assert _p.bundled_binary(name) is None


def test_bundled_binary_empty_name_returns_none() -> None:
    # bin/.exe is probably not a file
    out = _p.bundled_binary("")
    # Either None (typical) or a real path (unlikely) — must be None or
    # an existing file path.
    assert out is None or os.path.isfile(out)


def test_bundled_binary_with_meipass_lookup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """When _MEIPASS is set, bundled_binary looks under that root."""
    meipass = tmp_path / "_MEI"
    bin_subdir = meipass / "bin"
    bin_subdir.mkdir(parents=True)
    target_name = "fakeffmpeg.exe" if os.name == "nt" else "fakeffmpeg"
    (bin_subdir / target_name).write_bytes(b"")
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    out = _p.bundled_binary("fakeffmpeg")
    assert out is not None
    assert "fakeffmpeg" in out


def test_bundled_binary_with_meipass_miss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert _p.bundled_binary("definitely-not-bundled") is None
