"""Extended coverage for ``core.health_check``.

Each individual check tested with mocked failure modes; ``run_all``
and ``first_failure`` behaviour exhaustively verified.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core import health_check as _hc


# ---------------------------------------------------------------- CheckResult


def test_check_result_is_frozen() -> None:
    r = _hc.CheckResult("x", True, "ok")
    with pytest.raises(Exception):
        r.name = "y"  # type: ignore[misc]


def test_check_result_default_suggestion_empty() -> None:
    r = _hc.CheckResult("x", True, "ok")
    assert r.suggestion == ""


def test_check_result_format_ok_no_suggestion() -> None:
    r = _hc.CheckResult("x", True, "ok", "ignored")
    text = r.format()
    assert "[OK]" in text
    assert "ignored" not in text  # suggestion suppressed on pass


def test_check_result_format_fail_with_suggestion() -> None:
    r = _hc.CheckResult("x", False, "bad", "fix it")
    text = r.format()
    assert "[FAIL]" in text
    assert "fix it" in text


def test_check_result_format_fail_no_suggestion() -> None:
    r = _hc.CheckResult("x", False, "bad")
    text = r.format()
    assert "[FAIL]" in text
    assert "→" not in text  # no arrow without suggestion


# ---------------------------------------------------------------- _check_python_version


def test_check_python_version_returns_check_result() -> None:
    r = _hc._check_python_version()
    assert isinstance(r, _hc.CheckResult)
    assert r.name == "python_version"


def test_check_python_version_passes_under_311(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocking version_info < (3, 11) → check FAILS."""
    fake_version = type("V", (), {})()
    fake_version_info = (3, 10, 5)
    monkeypatch.setattr(sys, "version_info", fake_version_info)
    r = _hc._check_python_version()
    assert r.ok is False
    assert "3.10" in r.detail


def test_check_python_version_passes_at_311(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 11, 0))
    r = _hc._check_python_version()
    assert r.ok is True


def test_check_python_version_passes_at_312(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 12, 1))
    r = _hc._check_python_version()
    assert r.ok is True


# ---------------------------------------------------------------- _check_ffmpeg


def test_check_ffmpeg_bundled_found() -> None:
    r = _hc._check_ffmpeg()
    # Repo ships ffmpeg in bin/.
    assert r.name == "ffmpeg"
    assert r.ok is True


def test_check_ffmpeg_missing_when_bin_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hc, "bundled_binary", lambda _n: None)
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda _n: None)
    r = _hc._check_ffmpeg()
    assert r.ok is False
    assert "not found" in r.detail.lower() or "ffmpeg" in r.detail.lower()


def test_check_ffmpeg_path_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """If bin/ is empty but PATH has ffmpeg, check passes."""
    monkeypatch.setattr(_hc, "bundled_binary", lambda _n: None)
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda _n: "/usr/bin/ffmpeg")
    r = _hc._check_ffmpeg()
    assert r.ok is True


# ---------------------------------------------------------------- _check_ffprobe


def test_check_ffprobe_bundled_found() -> None:
    r = _hc._check_ffprobe()
    assert r.name == "ffprobe"
    # ffprobe is bundled; check should pass.
    assert r.ok is True


def test_check_ffprobe_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hc, "bundled_binary", lambda _n: None)
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda _n: None)
    r = _hc._check_ffprobe()
    assert r.ok is False


def test_check_ffprobe_subprocess_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """ffprobe present but `-version` times out → FAIL."""
    monkeypatch.setattr(_hc, "bundled_binary", lambda _n: "/fake/ffprobe")
    import subprocess
    def boom(*_a, **_kw):
        raise subprocess.TimeoutExpired(cmd="x", timeout=5)
    monkeypatch.setattr(subprocess, "run", boom)
    r = _hc._check_ffprobe()
    assert r.ok is False
    assert "ffprobe" in r.detail.lower()


def test_check_ffprobe_subprocess_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hc, "bundled_binary", lambda _n: "/fake/ffprobe")
    import subprocess
    def boom(*_a, **_kw):
        raise OSError("permission denied")
    monkeypatch.setattr(subprocess, "run", boom)
    r = _hc._check_ffprobe()
    assert r.ok is False


def test_check_ffprobe_subprocess_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """ffprobe -version returns non-zero exit → FAIL."""
    monkeypatch.setattr(_hc, "bundled_binary", lambda _n: "/fake/ffprobe")
    import subprocess
    class _FakeResult:
        returncode = 7
        stdout = ""
        stderr = "broken"
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeResult())
    r = _hc._check_ffprobe()
    assert r.ok is False
    assert "7" in r.detail


def test_check_ffprobe_subprocess_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hc, "bundled_binary", lambda _n: "/fake/ffprobe")
    import subprocess
    class _FakeResult:
        returncode = 0
        stdout = "ffprobe version 5.1"
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeResult())
    r = _hc._check_ffprobe()
    assert r.ok is True


# ---------------------------------------------------------------- _check_disk_writable


def test_check_disk_writable_normal() -> None:
    r = _hc._check_disk_writable()
    assert r.ok is True
    assert r.name == "disk_writable"


def test_check_disk_writable_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force tempfile.NamedTemporaryFile to raise OSError."""
    import tempfile
    def boom(*_a, **_kw):
        raise OSError("read-only filesystem")
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", boom)
    r = _hc._check_disk_writable()
    assert r.ok is False
    assert "could not write" in r.detail


def test_check_disk_writable_mkdir_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """mkdir raising OSError must surface as FAIL."""
    from core import config as _cfg
    real_dir = _cfg.user_config_dir()

    class _BadPath:
        def __init__(self, p: Path) -> None:
            self._p = p

        def mkdir(self, **_kw) -> None:
            raise OSError("read-only")

        def __truediv__(self, _other: object) -> "_BadPath":
            return self

        def __fspath__(self) -> str:
            return str(self._p)

        def __str__(self) -> str:
            return str(self._p)

    monkeypatch.setattr(_hc, "user_config_dir", lambda: _BadPath(real_dir))
    r = _hc._check_disk_writable()
    assert r.ok is False


# ---------------------------------------------------------------- _check_config_valid


def test_check_config_valid_normal() -> None:
    r = _hc._check_config_valid()
    assert r.name == "config"


def test_check_config_valid_load_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hc, "load_config", lambda: (_ for _ in ()).throw(
        RuntimeError("config load failed"),
    ))
    r = _hc._check_config_valid()
    assert r.ok is False
    assert "config" in r.detail.lower()


def test_check_config_valid_missing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """If load_config returns a dict lacking required keys → FAIL."""
    monkeypatch.setattr(_hc, "load_config", lambda: {"only_this": 1})
    r = _hc._check_config_valid()
    assert r.ok is False
    assert "missing" in r.detail.lower()


def test_check_config_valid_all_keys_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hc, "load_config", lambda: {
        "model": {}, "model_path": "/x", "output_formats": [],
    })
    r = _hc._check_config_valid()
    assert r.ok is True


# ---------------------------------------------------------------- _check_hub_configured


def test_check_hub_configured_not_set() -> None:
    r = _hc._check_hub_configured()
    assert r.name == "hub_folder"
    # Always OK — unconfigured triggers first-run dialog instead.
    assert r.ok is True


def test_check_hub_configured_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hc, "load_config", lambda: {"hub_folder": "/tmp/hub"})
    r = _hc._check_hub_configured()
    assert r.ok is True
    assert "/tmp/hub" in r.detail


# ---------------------------------------------------------------- _check_model_accessible


def test_check_model_accessible_blank_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hc, "load_config", lambda: {"model_path": ""})
    r = _hc._check_model_accessible()
    assert r.ok is True
    assert "not downloaded" in r.detail


def test_check_model_accessible_missing_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _hc, "load_config",
        lambda: {"model_path": str(tmp_path / "nope")},
    )
    r = _hc._check_model_accessible()
    assert r.ok is True  # benign — download fires on Transcribe
    assert "not yet present" in r.detail


def test_check_model_accessible_path_is_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = tmp_path / "notdir"
    f.write_bytes(b"x")
    monkeypatch.setattr(_hc, "load_config", lambda: {"model_path": str(f)})
    r = _hc._check_model_accessible()
    assert r.ok is False
    assert "not a directory" in r.detail


def test_check_model_accessible_missing_model_bin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "model"
    folder.mkdir()
    monkeypatch.setattr(
        _hc, "load_config", lambda: {"model_path": str(folder)},
    )
    r = _hc._check_model_accessible()
    assert r.ok is False
    assert "model.bin" in r.detail


def test_check_model_accessible_has_model_bin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "model"
    folder.mkdir()
    (folder / "model.bin").write_bytes(b"weights")
    monkeypatch.setattr(_hc, "load_config", lambda: {"model_path": str(folder)})
    r = _hc._check_model_accessible()
    assert r.ok is True


def test_check_model_accessible_finds_nested_model_bin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "model"
    nested = folder / "snapshots" / "abc"
    nested.mkdir(parents=True)
    (nested / "model.bin").write_bytes(b"weights")
    monkeypatch.setattr(_hc, "load_config", lambda: {"model_path": str(folder)})
    r = _hc._check_model_accessible()
    assert r.ok is True


# ---------------------------------------------------------------- _check_faster_whisper_importable


def test_check_faster_whisper_importable() -> None:
    r = _hc._check_faster_whisper_importable()
    # faster-whisper is in requirements.txt → should import.
    assert r.ok is True


def test_check_faster_whisper_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib
    def boom(name: str) -> None:
        if name == "faster_whisper":
            raise ImportError("not installed")
    monkeypatch.setattr(importlib, "import_module", boom)
    r = _hc._check_faster_whisper_importable()
    assert r.ok is False


# ---------------------------------------------------------------- run_all


def test_run_all_returns_results_for_every_check() -> None:
    results = _hc.run_all()
    assert len(results) == len(_hc.CHECKS)


def test_run_all_results_are_check_results() -> None:
    for r in _hc.run_all():
        assert isinstance(r, _hc.CheckResult)
        assert isinstance(r.name, str) and r.name
        assert isinstance(r.ok, bool)


def test_run_all_check_crash_becomes_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A check that itself raises is converted to a FAIL result."""
    def boom() -> _hc.CheckResult:
        raise RuntimeError("self-check crashed")
    monkeypatch.setattr(_hc, "CHECKS", [boom])
    results = _hc.run_all()
    assert len(results) == 1
    assert results[0].ok is False
    assert "crashed" in results[0].detail or "check itself" in results[0].detail


# ---------------------------------------------------------------- first_failure


def test_first_failure_empty_list() -> None:
    assert _hc.first_failure([]) is None


def test_first_failure_all_pass() -> None:
    rs = [_hc.CheckResult(f"x{i}", True, "ok") for i in range(5)]
    assert _hc.first_failure(rs) is None


def test_first_failure_returns_first() -> None:
    rs = [
        _hc.CheckResult("a", True, "ok"),
        _hc.CheckResult("b", False, "bad"),
        _hc.CheckResult("c", False, "also bad"),
    ]
    assert _hc.first_failure(rs).name == "b"  # type: ignore[union-attr]


def test_first_failure_single_failure() -> None:
    rs = [_hc.CheckResult("only", False, "x")]
    assert _hc.first_failure(rs).name == "only"  # type: ignore[union-attr]


# ---------------------------------------------------------------- format_report


def test_format_report_header_present() -> None:
    out = _hc.format_report([])
    assert "Whisper Project — basic — diagnostics report" in out


def test_format_report_includes_all_names() -> None:
    rs = [
        _hc.CheckResult("alpha", True, "ok"),
        _hc.CheckResult("beta", False, "broken"),
    ]
    out = _hc.format_report(rs)
    assert "alpha" in out
    assert "beta" in out


def test_format_report_ends_with_newline() -> None:
    out = _hc.format_report([_hc.CheckResult("x", True, "ok")])
    assert out.endswith("\n")


def test_format_report_empty_results() -> None:
    out = _hc.format_report([])
    # Just the header + blank, then trailing newline.
    assert out.count("\n") >= 2


def test_format_report_includes_fail_arrow() -> None:
    out = _hc.format_report([_hc.CheckResult("x", False, "bad", "fix")])
    assert "→" in out
    assert "fix" in out
