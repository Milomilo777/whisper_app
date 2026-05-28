"""Tests for app.services.format_service robustness (audit finding [8]).

The format-lookup poll() runs on the Tk main thread and re-arms itself at
the END of its body. Before the fix, an exception while handling one event
(e.g. yt-dlp JSON that decoded to a non-dict) escaped poll() and the
after-chain was never rescheduled — so ALL format lookups silently died
for the rest of the session. poll() is now self-healing.
"""
from __future__ import annotations

from queue import Queue

import pytest

from app.services.format_service import FormatService


class _Var:
    def __init__(self, value=""):
        self._v = value

    def get(self):
        return self._v

    def set(self, value):
        self._v = value


class _FakeApp:
    def __init__(self):
        self.download_url_var = _Var("http://x")
        self.format_status_var = _Var()
        self.format_events: Queue = Queue()
        self._closing = False
        self.after_calls: list = []

    def after(self, ms, fn):
        self.after_calls.append((ms, fn))


def test_handle_event_non_dict_payload_raises():
    svc = FormatService(_FakeApp())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        svc._handle_event("formats", "http://x", ["not", "a", "dict"])


def test_handle_event_error_sets_status():
    app = _FakeApp()
    FormatService(app)._handle_event(  # type: ignore[arg-type]
        "error", "http://x", "boom")
    assert app.format_status_var.get() == "boom"


def test_poll_self_heals_on_bad_event():
    app = _FakeApp()
    svc = FormatService(app)  # type: ignore[arg-type]
    app.format_events.put(("formats", "http://x", 12345))  # non-dict → raises

    svc.poll()  # must NOT propagate

    # poll re-armed itself despite the bad event...
    assert any(fn == svc.poll for (_ms, fn) in app.after_calls), \
        "poll() must reschedule even after an event handler raised"
    # ...and surfaced a message instead of dying silently.
    assert "Could not read formats" in app.format_status_var.get()


def test_poll_does_not_reschedule_when_closing():
    app = _FakeApp()
    app._closing = True
    svc = FormatService(app)  # type: ignore[arg-type]
    svc.poll()
    assert app.after_calls == [], "a closing app must not re-arm the poll loop"
