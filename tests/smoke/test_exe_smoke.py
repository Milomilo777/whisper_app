"""Smoke test for the built portable exe.

Skipped unless ``WHISPER_SMOKE_EXE`` points at the built artefact.
"""
from __future__ import annotations

import os
import subprocess

import pytest

SMOKE_EXE = os.environ.get("WHISPER_SMOKE_EXE", "")


@pytest.mark.skipif(not SMOKE_EXE, reason="WHISPER_SMOKE_EXE not set")
def test_exe_starts_and_responds_to_help() -> None:
    # The exe with --worker should print 'ready' (or 'startup_error')
    # on stdout within a few seconds.
    proc = subprocess.Popen(
        [SMOKE_EXE, "--worker"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Read one event.
        line = proc.stdout.readline().strip() if proc.stdout else ""
    finally:
        try:
            if proc.stdin is not None:
                import json
                proc.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    assert line, "worker emitted no events"
    assert '"event"' in line
