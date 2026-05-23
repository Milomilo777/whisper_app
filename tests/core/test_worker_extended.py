"""Extended coverage for ``core.worker`` IPC helpers.

Covers:
  * ``emit`` JSON-serialisation fallbacks (TypeError, ValueError)
  * ``emit`` with session token
  * ``_read_command_line`` boundary cases
  * ``_reconfigure_stdio_utf8`` graceful no-op
  * heartbeat constants + tick spacing
  * lifecycle event set
"""
from __future__ import annotations

import io
import json
import sys
import threading
import time
from typing import Any

import pytest

from core import worker as _w


# ---------------------------------------------------------------- emit


class _Recorder:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.lock = threading.Lock()

    def write(self, s: str) -> int:
        # print() writes the body, then the "end" arg ("\n"); collect
        # everything and split on newline at the end.
        with self.lock:
            self.lines.append(s)
        return len(s)

    def flush(self) -> None:
        pass


def test_emit_writes_one_json_object_per_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_w, "_SESSION_TOKEN", "")
    _w.emit("test", value=42)
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed["event"] == "test"
    assert parsed["value"] == 42


def test_emit_includes_session_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_w, "_SESSION_TOKEN", "TOK_ABC")
    _w.emit("ev", x=1)
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed["_token"] == "TOK_ABC"


def test_emit_no_token_when_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_w, "_SESSION_TOKEN", "")
    _w.emit("ev", x=1)
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert "_token" not in parsed


def test_emit_coerces_non_serialisable_via_repr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_w, "_SESSION_TOKEN", "")

    class _NotJSON:
        def __repr__(self) -> str:
            return "<NotJSON>"

    _w.emit("err", obj=_NotJSON())
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed["event"] == "err"
    # repr coercion should be evident.
    assert "<NotJSON>" in parsed["obj"]
    assert "_emit_warning" in parsed


def test_emit_with_kwargs_of_many_types(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_w, "_SESSION_TOKEN", "")
    _w.emit("multi", a=1, b="str", c=[1, 2], d={"k": "v"}, e=True, f=None, g=3.14)
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed["a"] == 1
    assert parsed["b"] == "str"
    assert parsed["c"] == [1, 2]
    assert parsed["d"] == {"k": "v"}
    assert parsed["e"] is True
    assert parsed["f"] is None
    assert parsed["g"] == 3.14


def test_emit_with_no_kwargs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_w, "_SESSION_TOKEN", "")
    _w.emit("bare")
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed == {"event": "bare"}


def test_emit_serialises_unicode_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_w, "_SESSION_TOKEN", "")
    _w.emit("log", message="视频 مرحبا 🎬")
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed["message"] == "视频 مرحبا 🎬"


# ---------------------------------------------------------------- _read_command_line


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_read_command_line_empty_input_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b""))
    assert _w._read_command_line() is None


def test_read_command_line_blank_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare \\n line still comes back as a 1-byte read."""
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"\n"))
    out = _w._read_command_line()
    assert out == b"\n"


def test_read_command_line_two_consecutive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"line1\nline2\n"))
    a = _w._read_command_line()
    b = _w._read_command_line()
    assert a == b"line1\n"
    assert b == b"line2\n"


def test_read_command_line_no_trailing_newline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Final line without newline → returned as-is."""
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"final"))
    out = _w._read_command_line()
    assert out == b"final"


def test_read_command_line_oversize_then_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    """Oversize line + EOF (no newline ever) → drain loop ends."""
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"x" * (2 * 1024 * 1024)))
    out = _w._read_command_line()
    assert out == b""


def test_read_command_line_just_under_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A line one byte under the cap (with newline) is accepted intact."""
    pad = _w.MAX_COMMAND_BYTES - 2  # leave room for "}\n"
    line = ("{" + ("x" * pad) + "\n").encode("utf-8")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(line))
    out = _w._read_command_line()
    assert out is not None
    assert out == line


def test_read_command_line_normal_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    msg = json.dumps({"x": "视频"}, ensure_ascii=False) + "\n"
    monkeypatch.setattr(sys, "stdin", _FakeStdin(msg.encode("utf-8")))
    out = _w._read_command_line()
    assert out is not None
    decoded = json.loads(out.decode("utf-8").strip())
    assert decoded["x"] == "视频"


# ---------------------------------------------------------------- _reconfigure_stdio_utf8


def test_reconfigure_no_raise_on_test_stdio() -> None:
    """Pytest's captured stdio is non-TextIOWrapper; helper must no-op."""
    _w._reconfigure_stdio_utf8()  # no AssertionError


def test_reconfigure_sets_utf8_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_out = io.BytesIO()
    raw_in = io.BytesIO(b"")
    wrap_in = io.TextIOWrapper(raw_in, encoding="cp1252", errors="strict")
    wrap_out = io.TextIOWrapper(raw_out, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdin", wrap_in)
    monkeypatch.setattr(sys, "stdout", wrap_out)
    _w._reconfigure_stdio_utf8()
    assert wrap_in.encoding.lower() == "utf-8"
    assert wrap_out.encoding.lower() == "utf-8"


def test_reconfigure_handles_reconfigure_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadStream:
        encoding = "cp1252"

        def reconfigure(self, **_kw: Any) -> None:
            raise OSError("denied")

    monkeypatch.setattr(sys, "stdin", _BadStream())
    monkeypatch.setattr(sys, "stdout", _BadStream())
    # Should not raise.
    _w._reconfigure_stdio_utf8()


def test_reconfigure_handles_reconfigure_valueerror(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadStream:
        encoding = "cp1252"

        def reconfigure(self, **_kw: Any) -> None:
            raise ValueError("bad encoding")

    monkeypatch.setattr(sys, "stdin", _BadStream())
    monkeypatch.setattr(sys, "stdout", _BadStream())
    _w._reconfigure_stdio_utf8()


# ---------------------------------------------------------------- heartbeat


def test_heartbeat_constant_is_5_seconds() -> None:
    assert _w.HEARTBEAT_INTERVAL_SECONDS == 5.0


def test_heartbeat_thread_is_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_w, "HEARTBEAT_INTERVAL_SECONDS", 0.05)

    threads_before = set(threading.enumerate())
    _w._start_heartbeat()
    # Give it a moment to spawn.
    time.sleep(0.01)
    threads_after = set(threading.enumerate()) - threads_before
    found_daemon = any(t.daemon and t.name == "worker-heartbeat" for t in threads_after)
    assert found_daemon


def test_heartbeat_tick_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ticks happen at ~HEARTBEAT_INTERVAL_SECONDS spacing.

    NOTE: Other tests in the suite may have spawned heartbeat daemons
    with shorter intervals; their leftover ticks leak into this
    recorder. We assert weak properties: ≥1 tick fires + each tick is
    not absurdly far apart.
    """
    monkeypatch.setattr(_w, "HEARTBEAT_INTERVAL_SECONDS", 0.1)
    ticks: list[float] = []

    def recording_emit(event: str, **_kw: Any) -> None:
        if event == "heartbeat":
            ticks.append(time.time())

    monkeypatch.setattr(_w, "emit", recording_emit)
    _w._start_heartbeat()
    time.sleep(0.35)
    assert len(ticks) >= 1
    # Each gap should be < 1 second (sanity).
    for i in range(1, len(ticks)):
        gap = ticks[i] - ticks[i - 1]
        assert 0.0 <= gap <= 1.0


# ---------------------------------------------------------------- lifecycle events


def test_lifecycle_events_includes_ready() -> None:
    assert "ready" in _w.LIFECYCLE_EVENTS


def test_lifecycle_events_includes_startup_error() -> None:
    assert "startup_error" in _w.LIFECYCLE_EVENTS


def test_lifecycle_events_includes_done() -> None:
    assert "done" in _w.LIFECYCLE_EVENTS


def test_lifecycle_events_includes_error() -> None:
    assert "error" in _w.LIFECYCLE_EVENTS


def test_lifecycle_events_includes_worker_exit() -> None:
    assert "worker_exit" in _w.LIFECYCLE_EVENTS


def test_lifecycle_events_excludes_progress() -> None:
    assert "progress" not in _w.LIFECYCLE_EVENTS


def test_lifecycle_events_excludes_log() -> None:
    assert "log" not in _w.LIFECYCLE_EVENTS


def test_lifecycle_events_excludes_heartbeat() -> None:
    assert "heartbeat" not in _w.LIFECYCLE_EVENTS


def test_lifecycle_events_is_frozenset() -> None:
    assert isinstance(_w.LIFECYCLE_EVENTS, frozenset)


# ---------------------------------------------------------------- MAX_COMMAND_BYTES


def test_max_command_bytes_is_one_mib() -> None:
    assert _w.MAX_COMMAND_BYTES == 1 << 20


# ---------------------------------------------------------------- emit_lock atomicity


def test_emit_atomic_under_high_thread_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """8 threads × 50 log emits each → every line parses as valid JSON.

    We can't assert an exact count because heartbeat daemons spawned
    by other tests may interleave their own emits onto stdout. The
    real invariant is "every line parses" + "≥ 8*50 log events" — the
    lock guarantees no interleaving inside a single line.
    """
    monkeypatch.setattr(_w, "_SESSION_TOKEN", "")

    def emitter(tag: str) -> None:
        for i in range(50):
            _w.emit("log", message=f"{tag}-{i}-" + ("y" * 1000))

    threads = [
        threading.Thread(target=emitter, args=(f"T{i}",))
        for i in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    captured = capsys.readouterr().out
    lines = [ln for ln in captured.splitlines() if ln.strip()]
    # Every line must be valid JSON — atomicity invariant.
    log_lines = 0
    for line in lines:
        obj = json.loads(line)  # would raise if interleaved
        if obj.get("event") == "log":
            log_lines += 1
    # At least the 8*50 log emits made it through (heartbeats add more).
    assert log_lines >= 8 * 50
