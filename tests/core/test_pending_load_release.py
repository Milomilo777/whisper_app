"""Audit C: the model-loading modal must close (and the headless waiter
unblock) when the awaited worker dies, not only on a 'ready' event ([1]);
and the poll() after()-chain must be single-owner (P2-1).
"""
from __future__ import annotations

import threading

from app.services.transcription_service import TranscriptionService


class _FakeApp:
    def __init__(self):
        self.after_calls: list = []
        self.posted: list = []

    def after(self, ms, fn):
        self.after_calls.append((ms, fn))

    def post_to_main(self, fn):
        self.posted.append(fn)


class _FakeDialog:
    def __init__(self):
        self.success = False

    def cancel(self):  # pragma: no cover - identity compared, not called
        self.success = False

    def mark_success_and_close(self):  # pragma: no cover
        self.success = True


def _svc():
    return TranscriptionService(_FakeApp())  # type: ignore[arg-type]


def test_release_on_worker_death_cancels_modal_and_unblocks_wait():
    svc = _svc()
    dialog = _FakeDialog()
    event = threading.Event()
    svc._pending_load_worker_id = 5
    svc._pending_load_dialog = dialog
    svc._pending_load_event = event

    svc._release_pending_load({"id": 5}, success=False)

    assert event.is_set()  # headless wait() returns
    assert svc.app.posted == [dialog.cancel]  # interactive modal cancelled
    # pending state cleared so a later event can't double-fire
    assert svc._pending_load_worker_id is None
    assert svc._pending_load_dialog is None
    assert svc._pending_load_event is None


def test_release_on_ready_closes_modal_with_success():
    svc = _svc()
    dialog = _FakeDialog()
    event = threading.Event()
    svc._pending_load_worker_id = 2
    svc._pending_load_dialog = dialog
    svc._pending_load_event = event

    svc._release_pending_load({"id": 2}, success=True)

    assert event.is_set()
    assert svc.app.posted == [dialog.mark_success_and_close]


def test_release_ignores_a_different_worker():
    svc = _svc()
    event = threading.Event()
    svc._pending_load_worker_id = 5
    svc._pending_load_event = event

    svc._release_pending_load({"id": 99}, success=False)

    assert not event.is_set()
    assert svc._pending_load_worker_id == 5  # untouched


def test_release_noop_when_nothing_pending():
    svc = _svc()
    svc._release_pending_load({"id": 1}, success=True)  # must not raise
    assert svc.app.posted == []


def test_ensure_poll_scheduled_coalesces():
    svc = _svc()
    svc._ensure_poll_scheduled()
    svc._ensure_poll_scheduled()
    svc._ensure_poll_scheduled()
    assert len(svc.app.after_calls) == 1  # only one chain booked

    # poll() clears the flag at its top; the next schedule books one more.
    svc._poll_scheduled = False
    svc._ensure_poll_scheduled()
    assert len(svc.app.after_calls) == 2
    # the scheduled callable is poll itself
    assert all(fn == svc.poll for _ms, fn in svc.app.after_calls)
