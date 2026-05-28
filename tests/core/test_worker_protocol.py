"""Tests for the worker JSON protocol — without spawning a subprocess.

We exercise ``core.worker.emit`` for serialization, then drive ``main()`` with
patched stdin/stdout and a stub transcriber to verify the event sequence.
"""
from __future__ import annotations

import io
import json
import sys

import pytest

from core import worker


def test_emit_serializes_event_and_payload(capsys):
    worker.emit("ready")
    line = capsys.readouterr().out.strip()
    parsed = json.loads(line)
    assert parsed == {"event": "ready"}


def test_emit_includes_extra_fields(capsys):
    worker.emit("progress", percent=42, message="hi")
    parsed = json.loads(capsys.readouterr().out.strip())
    assert parsed == {"event": "progress", "percent": 42, "message": "hi"}


def test_emit_progress_payload_keys(capsys):
    worker.emit("done", file_path="/tmp/x.wav")
    parsed = json.loads(capsys.readouterr().out.strip())
    assert parsed["event"] == "done"
    assert parsed["file_path"] == "/tmp/x.wav"


def test_main_emits_startup_error_when_model_missing(monkeypatch, capsys):
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    rc = worker.main()
    assert rc == 1
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    assert any(e["event"] == "startup_error" for e in events)


def test_main_emits_ready_then_handles_shutdown(monkeypatch, capsys):
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"action": "shutdown"}) + "\n"))
    rc = worker.main()
    assert rc == 0
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    assert events[0]["event"] == "ready"


def test_main_rejects_invalid_json_command(monkeypatch, capsys):
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)
    inputs = "not-json\n" + json.dumps({"action": "shutdown"}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(inputs))
    rc = worker.main()
    assert rc == 0
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    error_events = [e for e in events if e["event"] == "error"]
    assert error_events and "Invalid worker command" in error_events[0]["message"]


def test_main_rejects_missing_file_path(monkeypatch, capsys):
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)
    inputs = json.dumps({"action": "transcribe"}) + "\n" + json.dumps({"action": "shutdown"}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(inputs))
    worker.main()
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    error_events = [e for e in events if e["event"] == "error"]
    assert error_events and "Missing input file" in error_events[0]["message"]


def test_main_emits_started_then_done_on_transcribe(monkeypatch, capsys):
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)
    monkeypatch.setattr(worker, "transcribe", lambda task, p, l, language_cb=None: None)
    inputs = json.dumps({"action": "transcribe", "file_path": "/tmp/x.wav"}) + "\n" + json.dumps({"action": "shutdown"}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(inputs))
    worker.main()
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    started = [e for e in events if e["event"] == "started"]
    done = [e for e in events if e["event"] == "done"]
    assert started and done
    assert started[0]["file_path"] == "/tmp/x.wav"


def test_main_done_event_includes_written_outputs(monkeypatch, capsys):
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)

    def fake_transcribe(task, p, l, language_cb=None):
        task.output_paths = ["/tmp/x.srt", "/tmp/x.docx"]

    monkeypatch.setattr(worker, "transcribe", fake_transcribe)
    inputs = json.dumps({"action": "transcribe", "file_path": "/tmp/x.wav"}) + "\n" + json.dumps({"action": "shutdown"}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(inputs))
    worker.main()
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    done = [e for e in events if e["event"] == "done"]
    assert done and done[0].get("outputs") == ["/tmp/x.srt", "/tmp/x.docx"]


def test_main_unknown_action_emits_error(monkeypatch, capsys):
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)
    inputs = json.dumps({"action": "fly-to-the-moon"}) + "\n" + json.dumps({"action": "shutdown"}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(inputs))
    worker.main()
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    error_events = [e for e in events if e["event"] == "error"]
    assert error_events and "Unknown worker command" in error_events[0]["message"]


def test_main_catches_transcribe_exception(monkeypatch, capsys):
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)
    def boom(*a, **k):
        raise RuntimeError("decode failed")
    monkeypatch.setattr(worker, "transcribe", boom)
    inputs = json.dumps({"action": "transcribe", "file_path": "/tmp/x.wav"}) + "\n" + json.dumps({"action": "shutdown"}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(inputs))
    worker.main()
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    error_events = [e for e in events if e["event"] == "error"]
    assert error_events and "decode failed" in error_events[0]["message"]


def test_main_rejects_oversize_command(monkeypatch, capsys):
    """Audit P2-20: a stdin line past MAX_COMMAND_BYTES is dropped with an
    error and never starts a task (OOM / runaway-parent guard)."""
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)
    monkeypatch.setattr(
        worker, "transcribe",
        lambda *a, **k: pytest.fail("oversize command must not run a task"),
    )
    # MAX_COMMAND_BYTES is a 1 MB local in worker.main(); exceed it.
    huge = "x" * ((1 << 20) + 10) + "\n"
    inputs = huge + json.dumps({"action": "shutdown"}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(inputs))
    worker.main()
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    errs = [e for e in events if e["event"] == "error"]
    assert errs and "exceeds max length" in errs[0]["message"]
    assert not any(e["event"] == "started" for e in events)


def test_main_clip_disables_resume(monkeypatch, capsys):
    """Audit P2-20: a clipped request must NOT resume a whole-file
    checkpoint (resuming would transcribe past clip_end)."""
    monkeypatch.setattr(worker, "load_existing_model", lambda cb: True)
    monkeypatch.setattr(
        worker, "resume_transcription",
        lambda *a, **k: pytest.fail("a clipped run must not call resume_transcription"),
    )
    ran = {"transcribe": False}

    def fake_transcribe(task, p, l, language_cb=None):
        ran["transcribe"] = True

    monkeypatch.setattr(worker, "transcribe", fake_transcribe)
    cmd = {
        "action": "transcribe", "file_path": "/tmp/x.wav",
        "clip_start": 10, "clip_end": 20, "resume": True,
    }
    inputs = json.dumps(cmd) + "\n" + json.dumps({"action": "shutdown"}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(inputs))
    worker.main()
    assert ran["transcribe"] is True  # full path ran, resume did not
    events = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines() if l.strip()]
    assert any(e["event"] == "done" for e in events)
