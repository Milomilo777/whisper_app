"""Tests for the shared error / retry helpers in core._errors."""
from __future__ import annotations

import logging
import time

import pytest

from core._errors import fmt_err, with_retries


# ---------- fmt_err -----------------------------------------------------------


def test_fmt_err_includes_type_and_message():
    exc = ValueError("bad input")
    assert fmt_err("Validation", exc) == "Validation failed: ValueError: bad input"


def test_fmt_err_includes_no_message_marker_when_exc_has_no_message():
    exc = RuntimeError()
    assert fmt_err("Run", exc) == "Run failed: RuntimeError: (no message)"


def test_fmt_err_handles_non_exception_input_gracefully():
    # In rare cases callers pass through a string (legacy code) — we
    # accept that and fall back to a simpler format.
    out = fmt_err("Step", "raw string oh no")  # type: ignore[arg-type]
    assert out == "Step failed: raw string oh no"


def test_fmt_err_preserves_unicode_messages():
    exc = ValueError("échec critique — vérifiez la configuration")
    assert "échec critique" in fmt_err("Test", exc)


# ---------- with_retries: happy path -----------------------------------------


def test_with_retries_returns_first_success_immediately():
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        return 42

    out = with_retries(_fn, attempts=3, backoff_seconds=0)
    assert out == 42
    assert calls["n"] == 1


def test_with_retries_returns_after_n_failures():
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("flaky")
        return "ok"

    out = with_retries(_fn, attempts=5, backoff_seconds=0)
    assert out == "ok"
    assert calls["n"] == 3


def test_with_retries_exhausts_and_reraises():
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        raise RuntimeError(f"fail {calls['n']}")

    with pytest.raises(RuntimeError, match="fail 3"):
        with_retries(_fn, attempts=3, backoff_seconds=0)
    assert calls["n"] == 3


def test_with_retries_logs_each_failure_and_exhaustion(caplog):
    def _fn():
        raise RuntimeError("kaboom")

    with caplog.at_level(logging.WARNING, logger="core._errors"):
        with pytest.raises(RuntimeError):
            with_retries(_fn, attempts=3, backoff_seconds=0, label="my-op")
    msgs = [r.getMessage() for r in caplog.records]
    # Two "attempt N/M failed" + one "exhausted retries" = 3 lines.
    assert sum("attempt" in m and "retrying" in m for m in msgs) == 2
    assert any("exhausted retries" in m for m in msgs)
    assert all("my-op" in m for m in msgs)


def test_with_retries_respects_retry_on_filter():
    """An exception type NOT in retry_on must propagate without retry."""
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        raise KeyError("nope")

    with pytest.raises(KeyError):
        with_retries(_fn, attempts=5, backoff_seconds=0,
                     retry_on=(ValueError,))
    assert calls["n"] == 1


def test_with_retries_rejects_zero_attempts():
    with pytest.raises(ValueError, match="attempts must be"):
        with_retries(lambda: None, attempts=0)


def test_with_retries_uses_callable_name_as_default_label(caplog):
    def my_named_thing():
        raise RuntimeError("nope")

    with caplog.at_level(logging.WARNING, logger="core._errors"):
        with pytest.raises(RuntimeError):
            with_retries(my_named_thing, attempts=2, backoff_seconds=0)
    rendered = " ".join(r.getMessage() for r in caplog.records)
    assert "my_named_thing" in rendered


def test_with_retries_backoff_is_applied(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    def _fn():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        with_retries(_fn, attempts=3, backoff_seconds=1.0,
                     backoff_multiplier=2.0)
    # Two sleeps (between attempts 1→2 and 2→3); multiplier doubles each.
    assert len(sleeps) == 2
    assert sleeps[0] == pytest.approx(1.0)
    assert sleeps[1] == pytest.approx(2.0)


def test_with_retries_skips_sleep_when_backoff_zero(monkeypatch):
    """``backoff_seconds=0`` is the test-time fast path; verify sleep
    is not invoked so tests stay snappy."""
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    def _fn():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        with_retries(_fn, attempts=3, backoff_seconds=0)
    assert sleeps == []
