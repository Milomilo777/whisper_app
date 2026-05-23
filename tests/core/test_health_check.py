"""Tests for ``core.health_check``."""
from __future__ import annotations

import pytest

from core import health_check as _hc


def test_check_python_version_ok() -> None:
    r = _hc._check_python_version()
    assert r.name == "python_version"
    assert r.ok is True


def test_check_disk_writable_ok() -> None:
    r = _hc._check_disk_writable()
    assert r.ok is True


def test_check_config_valid_ok() -> None:
    r = _hc._check_config_valid()
    assert r.ok is True


def test_run_all_returns_one_per_check() -> None:
    results = _hc.run_all()
    assert len(results) == len(_hc.CHECKS)
    for r in results:
        assert isinstance(r.name, str) and r.name
        assert isinstance(r.ok, bool)


def test_format_report_renders_each_result() -> None:
    results = _hc.run_all()
    out = _hc.format_report(results)
    for r in results:
        assert r.name in out
    assert out.startswith("Whisper Project — basic — diagnostics report")


def test_first_failure_returns_none_when_all_ok() -> None:
    ok = [_hc.CheckResult("x", True, "fine")]
    assert _hc.first_failure(ok) is None


def test_first_failure_returns_first_fail() -> None:
    results = [
        _hc.CheckResult("a", True, "ok"),
        _hc.CheckResult("b", False, "broken", suggestion="fix it"),
        _hc.CheckResult("c", False, "also broken"),
    ]
    f = _hc.first_failure(results)
    assert f is not None and f.name == "b"


def test_result_format_includes_suggestion_on_fail() -> None:
    r = _hc.CheckResult("x", False, "bad", suggestion="reboot")
    text = r.format()
    assert "FAIL" in text
    assert "reboot" in text


def test_result_format_omits_suggestion_on_pass() -> None:
    r = _hc.CheckResult("x", True, "good", suggestion="ignored")
    text = r.format()
    assert "OK" in text
    assert "ignored" not in text
