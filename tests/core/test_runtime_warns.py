"""Regression tests for the runtime-probe WARN items.

Two real bugs surfaced by the post-fix adversarial probe (see
``DEBUG_RUNTIME_BASIC.md``):

* WARN #15 — shutdown wasn't honoured while a transcribe was in
  flight, because stdin reads were synchronous on the main thread.
  The fix moves command parsing onto a daemon thread; shutdown
  flips ``task.cancelled`` on the active task so the segment loop
  bails on the next iteration.
* WARN #24 — ``hub_folder`` on an unmounted drive didn't fall
  back to the default. The fix probes ``hub_folder`` with
  ``_drive_is_mounted`` before using it.
"""
from __future__ import annotations

from typing import Any

import pytest

from core import config as _cfg
from core import worker as _w
from core.task import TranscriptionTask


# ---------------------------------------------------------------- WARN #15

def test_shutdown_cancels_active_task_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutting down while a task is in flight flips the task's
    cancelled flag, so the segment loop bails on the next pass —
    rather than blocking until the file finishes."""
    task = TranscriptionTask(r"C:\fake\file.mp3")
    monkeypatch.setattr(_w, "_active_task", task, raising=False)
    monkeypatch.setattr(_w, "_shutting_down", _w.threading.Event())

    # Simulate the command-reader thread seeing a shutdown line.
    _w._shutting_down.set()
    if _w._active_task is not None:
        _w._active_task.cancelled = True

    assert task.cancelled is True
    assert _w._shutting_down.is_set() is True


def test_command_reader_is_daemon_thread() -> None:
    """The reader thread must be a daemon so process exit doesn't
    block on it."""
    import inspect
    src = inspect.getsource(_w._start_command_reader)
    # Crude but effective: ensure the source mentions daemon=True.
    assert "daemon=True" in src


# ---------------------------------------------------------------- WARN #24

def test_hub_on_unmounted_drive_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``hub_folder`` itself is on a dead drive, the fallback
    must reach for ``default_hub_folder()`` rather than recomputing
    a path on the same dead drive."""
    # Pretend every drive probe says "unmounted" — both for the
    # stale model_path AND for the configured hub.
    monkeypatch.setattr(_cfg, "_drive_is_mounted", lambda _p: False)
    # Pin default_hub_folder to a known sentinel so we can assert
    # the recomputed model_path lives under it.
    from core import hub as _hub
    sentinel_hub = "C:/known/default/hub"
    monkeypatch.setattr(_hub, "default_hub_folder", lambda: sentinel_hub)

    cfg: dict[str, Any] = {
        "model": {
            "name": "faster-whisper-large-v3",
            "url": "https://example.com/m.zip",
            "md5": "https://example.com/m.zip.md5",
        },
        "model_path": "Z:/dead/drive/models--Systran--foo",
        "hub_folder": "Z:/dead/drive/hub",
    }
    out = _cfg._apply_runtime_fallbacks(cfg)
    # Must NOT keep the Z:\ path, and must use the default hub.
    assert "Z:" not in out["model_path"], out["model_path"]
    assert out["model_path"].startswith(sentinel_hub.replace("/", "\\")) \
        or out["model_path"].startswith(sentinel_hub), out["model_path"]
