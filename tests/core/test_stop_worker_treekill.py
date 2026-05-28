"""stop_worker must tree-kill (not bare terminate/kill) so the worker's
grandchild ffmpeg/demucs dies with it (audit finding [2]).
"""
from __future__ import annotations

import subprocess
import threading

from app.services import transcription_service as ts


class _FakeStdin:
    def write(self, _s):  # pragma: no cover - trivial
        pass

    def flush(self):  # pragma: no cover - trivial
        pass


class _StubbornProc:
    """A worker that ignores graceful shutdown and never exits on wait()."""

    pid = 12345
    stdin = _FakeStdin()

    def poll(self):
        return None  # always "alive"

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout or 0.0)


def test_stop_worker_escalates_to_tree_kill(monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(
        ts, "kill_process_tree", lambda proc, force=False: calls.append(force)
    )
    svc = ts.TranscriptionService(app=None)  # type: ignore[arg-type]
    worker = {"id": 7, "process": _StubbornProc(), "stdin_lock": threading.Lock()}

    svc.stop_worker(worker)

    # graceful stdin shutdown timed out → tree-terminate, then tree-kill.
    assert calls == [False, True]


def test_stop_worker_noop_when_already_dead(monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(
        ts, "kill_process_tree", lambda proc, force=False: calls.append(force)
    )

    class _Dead:
        pid = 1
        stdin = _FakeStdin()

        def poll(self):
            return 0  # exited

    svc = ts.TranscriptionService(app=None)  # type: ignore[arg-type]
    svc.stop_worker({"id": 1, "process": _Dead(), "stdin_lock": threading.Lock()})
    assert calls == []  # nothing to kill
