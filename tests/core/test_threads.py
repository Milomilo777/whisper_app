"""Tests for the safe_thread helper in core._threads."""
from __future__ import annotations

import logging
import threading
import time

import pytest

from core._threads import safe_thread


def _wait_for(condition, timeout=2.0):
    """Tiny poll helper — fail loud if the condition never becomes true."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


# ---------- happy path --------------------------------------------------------


def test_safe_thread_runs_target_with_args():
    done = threading.Event()
    captured: dict = {}

    def _target(a, b, *, key):
        captured["a"] = a
        captured["b"] = b
        captured["key"] = key
        done.set()

    safe_thread(_target, args=(1, 2), kwargs={"key": "value"}, name="t1")
    assert _wait_for(done.is_set), "target never ran"
    assert captured == {"a": 1, "b": 2, "key": "value"}


def test_safe_thread_returns_thread_object():
    done = threading.Event()

    def _target():
        done.set()

    t = safe_thread(_target, name="returned")
    assert isinstance(t, threading.Thread)
    assert t.name == "returned"
    assert _wait_for(done.is_set)


def test_safe_thread_defaults_to_daemon_true():
    def _target():
        return None

    t = safe_thread(_target, start=False)
    assert t.daemon is True


def test_safe_thread_respects_daemon_false():
    def _target():
        return None

    t = safe_thread(_target, daemon=False, start=False)
    assert t.daemon is False


def test_safe_thread_start_false_does_not_launch():
    started = threading.Event()

    def _target():
        started.set()

    t = safe_thread(_target, start=False)
    # Give a tick to make sure it didn't auto-start.
    time.sleep(0.05)
    assert not started.is_set()
    assert not t.is_alive()
    t.start()
    assert _wait_for(started.is_set)


def test_safe_thread_name_defaults_to_target_dunder_name():
    def _my_named_worker():
        return None

    t = safe_thread(_my_named_worker, start=False)
    assert t.name == "_my_named_worker"


# ---------- failure path ------------------------------------------------------


def test_safe_thread_logs_exception_when_target_raises(caplog):
    crashed = threading.Event()

    def _explode():
        crashed.set()
        raise ValueError("kaboom")

    with caplog.at_level(logging.ERROR, logger="core._threads"):
        t = safe_thread(_explode, name="explode-worker")
        assert _wait_for(crashed.is_set)
        # Give the wrapper a moment to log + the thread to exit.
        t.join(timeout=2.0)

    # The exception type + message + thread name must all appear.
    rendered = " ".join(record.getMessage() for record in caplog.records)
    assert "explode-worker" in rendered
    # logger.exception() emits the traceback as part of the record;
    # the message itself is the format string we wrote.
    assert any(
        record.levelno == logging.ERROR for record in caplog.records
    )
    # Stack-info / exception info must be attached so consumers
    # (sentry, log files) can recover the actual exception type.
    assert any(
        record.exc_info is not None for record in caplog.records
    ), "logger.exception should attach exc_info"


def test_safe_thread_failure_does_not_propagate_to_caller():
    def _explode():
        raise RuntimeError("nope")

    # The caller should not see the exception — it must be contained
    # by the wrapper. Construction + start must return cleanly.
    t = safe_thread(_explode, name="contained")
    t.join(timeout=2.0)
    assert not t.is_alive()


def test_safe_thread_failure_marks_thread_as_finished():
    """Failed threads must still exit cleanly so the process can
    reap them — no zombie threads."""
    def _explode():
        raise RuntimeError("nope")

    t = safe_thread(_explode, name="must-die")
    assert _wait_for(lambda: not t.is_alive())
