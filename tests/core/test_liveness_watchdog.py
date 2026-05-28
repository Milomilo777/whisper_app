"""Audit P2-18: poll()'s liveness watchdog must restart a worker that has
stopped emitting events (incl. its 5 s heartbeat) past LIVENESS_TIMEOUT_S,
finishing any in-flight task as an error first. A fresh worker is untouched.
"""
from __future__ import annotations

from queue import Queue

from app.services.transcription_service import TranscriptionService


class _AliveProc:
    def __init__(self, pid=1):
        self.pid = pid

    def poll(self):
        return None  # still running


class _FakeApp:
    def __init__(self, workers):
        self.workers = workers
        self.worker_events: Queue = Queue()  # empty → straight to watchdog
        self.after_calls: list = []
        self.logs: list = []

    def after(self, ms, fn):
        self.after_calls.append((ms, fn))

    def log(self, msg):
        self.logs.append(msg)


class _Task:
    def __init__(self):
        self.status = "running"


def test_watchdog_restarts_stale_worker_and_leaves_fresh_one(monkeypatch):
    stale = {"id": 1, "process": _AliveProc(1), "task": _Task(),
             "last_event_at": 1.0}  # epoch — ancient
    fresh = {"id": 2, "process": _AliveProc(2), "task": None}
    svc = TranscriptionService(_FakeApp([stale, fresh]))  # type: ignore[arg-type]
    # Stamp the fresh worker as just-seen so it is NOT reaped.
    import time as _t
    fresh["last_event_at"] = _t.time()

    restarted: list = []
    finished: list = []
    monkeypatch.setattr(svc, "restart_worker", lambda w: restarted.append(w["id"]))
    monkeypatch.setattr(
        svc, "finish_task",
        lambda w, keep_status=False: finished.append((w["id"], keep_status)),
    )

    svc.poll()

    assert restarted == [1], "the stale worker must be restarted"
    assert (1, True) in finished, "its running task must be finished with keep_status"
    assert 2 not in restarted, "a fresh worker must be left alone"


def test_watchdog_ignores_worker_with_zero_timestamp(monkeypatch):
    # last_event_at == 0.0 is the 'never stamped' sentinel — the `if last`
    # guard skips it so a just-spawned worker isn't reaped before its first
    # event.
    w = {"id": 9, "process": _AliveProc(9), "task": None, "last_event_at": 0.0}
    svc = TranscriptionService(_FakeApp([w]))  # type: ignore[arg-type]
    restarted: list = []
    monkeypatch.setattr(svc, "restart_worker", lambda x: restarted.append(x["id"]))
    svc.poll()
    assert restarted == []
