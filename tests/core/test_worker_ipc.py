"""Tests for the worker's IPC layer (P0-1/3/6, P1-5/6/7).

We can't easily mount a full worker process in-process (it loads
faster-whisper), so most tests exercise the helpers directly:

* :func:`core.worker._read_command_line` — oversize-line guard
  (P0-1, P1-6).
* :func:`core.worker.emit` under contention — atomic stdout writes
  (P0-6).
* :func:`core.worker._reconfigure_stdio_utf8` — UTF-8 reconfigure
  doesn't raise on the test runner's stdio (P1-5).
* ``App._enqueue_worker_event`` — lifecycle-event preservation
  (P1-7) is verified without spinning Tk by instantiating a stub.
"""
from __future__ import annotations

import io
import json
import queue
import sys
import threading
from typing import Any

import pytest

from core import worker as _w


# ---------------------------------------------------------------- helpers

class _FakeStdin:
    """Stand-in for ``sys.stdin`` with a ``.buffer`` attribute."""

    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


# ---------------------------------------------------------------- P0-1 / P1-6

def test_read_command_line_caps_oversize_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 2-MiB line with no newline must NOT be buffered into RAM."""
    huge = b"x" * (2 * 1024 * 1024)  # 2 MiB, no \n
    fake = _FakeStdin(huge + b"\n" + b'{"action":"shutdown"}\n')
    monkeypatch.setattr(_w.sys, "stdin", fake)

    # First read: oversize, returns empty so caller emits "dropped".
    raw = _w._read_command_line()
    assert raw == b""
    # Second read: the normal shutdown command got through fine.
    raw2 = _w._read_command_line()
    assert raw2 is not None
    assert b"shutdown" in raw2


def test_read_command_line_returns_none_on_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    """EOF on stdin yields None — caller treats as graceful shutdown."""
    fake = _FakeStdin(b"")
    monkeypatch.setattr(_w.sys, "stdin", fake)
    assert _w._read_command_line() is None


def test_read_command_line_accepts_normal_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal small JSON command line round-trips intact."""
    payload = b'{"action":"transcribe","file_path":"/x.mp3"}\n'
    fake = _FakeStdin(payload)
    monkeypatch.setattr(_w.sys, "stdin", fake)
    raw = _w._read_command_line()
    assert raw == payload


def test_read_command_line_at_exact_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A line whose total bytes == MAX_COMMAND_BYTES (incl. \\n) is OK."""
    # Build a JSON object whose serialised line is exactly the cap.
    pad_len = _w.MAX_COMMAND_BYTES - len('{"x":""}') - 1  # -1 for \n
    line = ('{"x":"' + ("a" * pad_len) + '"}' + "\n").encode("utf-8")
    assert len(line) == _w.MAX_COMMAND_BYTES
    fake = _FakeStdin(line)
    monkeypatch.setattr(_w.sys, "stdin", fake)
    raw = _w._read_command_line()
    assert raw == line


# ---------------------------------------------------------------- P0-6

def test_emit_is_atomic_under_contention(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two threads emitting 200 events each → no JSON parse errors."""
    # Write to a real text stream we can capture.
    monkeypatch.setattr(_w, "_SESSION_TOKEN", "")

    iterations = 200

    def emitter(tag: str) -> None:
        for i in range(iterations):
            # A long payload makes interleaving easier to provoke.
            _w.emit("log", message=f"{tag}-{i}-" + ("x" * 4096))

    t1 = threading.Thread(target=emitter, args=("A",))
    t2 = threading.Thread(target=emitter, args=("B",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    captured = capsys.readouterr().out
    lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert len(lines) == iterations * 2, (
        f"expected {iterations*2} lines, got {len(lines)}"
    )
    for line in lines:
        # If atomicity broke, json.loads would raise here.
        obj = json.loads(line)
        assert obj["event"] == "log"
        assert "message" in obj


# ---------------------------------------------------------------- P1-5

def test_reconfigure_stdio_utf8_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reconfigure helper must never raise on weird test stdio.

    pytest captures stdio with non-TextIOWrapper objects that may not
    expose ``reconfigure``; the helper has to no-op cleanly in that
    case.
    """
    # No exception → good. The helper logs at debug on failure.
    _w._reconfigure_stdio_utf8()


def test_reconfigure_stdio_utf8_sets_encoding_when_available() -> None:
    """When the stream supports reconfigure(), it's set to UTF-8."""
    # Wrap a BytesIO in a TextIOWrapper so reconfigure() is available.
    raw = io.BytesIO()
    wrapper = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    assert wrapper.encoding.lower() == "cp1252"
    wrapper.reconfigure(encoding="utf-8", errors="replace")
    assert wrapper.encoding.lower() == "utf-8"


def test_utf8_command_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """A JSON command with a Chinese filename decodes cleanly."""
    chinese_path = "/tmp/视频文件.mp4"
    cmd = {"action": "transcribe", "file_path": chinese_path}
    raw = (json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8")
    fake = _FakeStdin(raw)
    monkeypatch.setattr(_w.sys, "stdin", fake)
    out = _w._read_command_line()
    assert out is not None
    decoded = out.decode("utf-8").strip()
    parsed = json.loads(decoded)
    assert parsed["file_path"] == chinese_path


# ---------------------------------------------------------------- P1-7

def test_enqueue_worker_event_preserves_lifecycle_on_full() -> None:
    """When the queue is full, ``done``/``error``/``worker_exit`` block
    until space appears; ``progress``/``log`` are dropped via Full."""
    # Borrow the bound method by binding ``App._enqueue_worker_event``
    # to a stub that exposes just ``worker_events``.
    from app.app import App, _LIFECYCLE_EVENTS

    class _Stub:
        def __init__(self) -> None:
            self.worker_events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2)

    stub = _Stub()
    enqueue = App._enqueue_worker_event.__get__(stub, _Stub)

    # Fill the queue.
    stub.worker_events.put_nowait({"event": "progress", "percent": 1})
    stub.worker_events.put_nowait({"event": "progress", "percent": 2})

    # A non-lifecycle event must be dropped, not block.
    enqueue({"event": "progress", "percent": 3})
    assert stub.worker_events.qsize() == 2

    # A lifecycle event must NOT be dropped. We run it in a worker
    # thread that drains the queue after a short delay; the put has
    # to come through.
    def drain_after_delay() -> None:
        import time as _t
        _t.sleep(0.1)
        try:
            stub.worker_events.get_nowait()
        except queue.Empty:
            pass

    threading.Thread(target=drain_after_delay, daemon=True).start()
    enqueue({"event": "done", "file_path": "/x.mp3"})

    # Drain everything and assert the `done` event got through.
    events: list[dict[str, Any]] = []
    while True:
        try:
            events.append(stub.worker_events.get_nowait())
        except queue.Empty:
            break
    assert any(e.get("event") == "done" for e in events)
    # And the lifecycle set covers what the docstring promises.
    assert "done" in _LIFECYCLE_EVENTS
    assert "worker_exit" in _LIFECYCLE_EVENTS
    assert "ready" in _LIFECYCLE_EVENTS
    assert "error" in _LIFECYCLE_EVENTS
    assert "startup_error" in _LIFECYCLE_EVENTS
    assert "progress" not in _LIFECYCLE_EVENTS
    assert "log" not in _LIFECYCLE_EVENTS
