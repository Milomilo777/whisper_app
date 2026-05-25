"""Tests for the worker's cooperative cancel/pause/resume control channel.

The worker reads stdin on a dedicated thread so it can apply control
commands to the in-flight task while the main thread is blocked inside
transcribe(). The transcriber polls ``task.cancelled`` / ``task.paused``
between segments. These tests cover the flag-flipping helpers and the
threaded routing (a control command reaching a running transcribe),
without a real Whisper model.
"""
from __future__ import annotations

import json
import threading
import types

import pytest

from core import worker


@pytest.fixture(autouse=True)
def _reset_current_task():
    """Never let _current_task leak between tests."""
    worker._set_current_task(None)
    yield
    worker._set_current_task(None)


def _task() -> types.SimpleNamespace:
    return types.SimpleNamespace(cancelled=False, paused=False)


def test_apply_control_cancel_sets_flag():
    t = _task()
    worker._set_current_task(t)
    worker._apply_control("cancel")
    assert t.cancelled is True


def test_apply_control_pause_then_resume():
    t = _task()
    worker._set_current_task(t)
    worker._apply_control("pause")
    assert t.paused is True
    worker._apply_control("resume")
    assert t.paused is False


def test_apply_control_without_current_task_is_noop():
    worker._set_current_task(None)
    # Must not raise.
    worker._apply_control("cancel")
    worker._apply_control("pause")
    worker._apply_control("resume")


def test_apply_control_unknown_action_is_noop():
    t = _task()
    worker._set_current_task(t)
    worker._apply_control("self-destruct")
    assert t.cancelled is False and t.paused is False


class _GatedStdin:
    """Iterable stdin stub. Yields the first line immediately, then
    blocks every subsequent line until ``gate`` is set — so a control
    command is only read AFTER the main thread has registered the task
    (the real-world ordering; avoids a false race in the test)."""

    def __init__(self, lines, gate: threading.Event):
        self._lines = list(lines)
        self._gate = gate
        self._i = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._i == 0:
            self._i += 1
            return self._lines[0]
        if not self._gate.wait(timeout=5.0):
            raise StopIteration
        if self._i < len(self._lines):
            line = self._lines[self._i]
            self._i += 1
            return line
        raise StopIteration


def test_control_command_cancels_running_transcribe(monkeypatch, capsys):
    """End-to-end through main(): a 'cancel' read on the reader thread
    reaches a transcribe that is actively polling task.cancelled."""
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)

    running = threading.Event()

    def fake_transcribe(task, progress_cb, log_cb, language_cb=None):
        # Simulate a long transcribe that honours cooperative cancel.
        running.set()  # tell the gated stdin it's safe to deliver 'cancel'
        for _ in range(500):  # ~5s max guard
            if task.cancelled:
                return
            threading.Event().wait(0.01)
        raise AssertionError("transcribe was never cancelled")

    monkeypatch.setattr(worker, "transcribe", fake_transcribe)

    lines = [
        json.dumps({"action": "transcribe", "file_path": "/tmp/x.wav"}) + "\n",
        json.dumps({"action": "cancel"}) + "\n",
        json.dumps({"action": "shutdown"}) + "\n",
    ]
    monkeypatch.setattr(worker.sys, "stdin", _GatedStdin(lines, running))

    rc = worker.main()
    assert rc == 0
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    kinds = [e["event"] for e in events]
    assert "started" in kinds and "done" in kinds
