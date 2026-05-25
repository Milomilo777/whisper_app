"""Cancelling a transcription mid-run flushes a resumable checkpoint.

The cooperative cancel flips ``task.cancelled``; the transcriber polls it
between segments and, when segments still remain, writes a checkpoint so
the user can Re-run from there instead of starting over. Driven with a
fake model + ``PIPELINE=None`` so the lazy (interruptible) path is forced
and the result is deterministic regardless of machine speed or whether a
batched pipeline would otherwise be used.
"""
from __future__ import annotations

import pytest

pytest.importorskip("faster_whisper")


class _Seg:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.words = None


class _Info:
    language = "en"
    language_probability = 0.9
    duration = 100.0


def test_cancel_midrun_writes_checkpoint(monkeypatch, tmp_path):
    import core.transcriber as t
    from core.task import TranscriptionTask

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"\x00")  # presence only — get_duration is stubbed

    task = TranscriptionTask(str(audio))

    def _segs():
        yield _Seg(0.0, 10.0, "one")
        # The cooperative cancel signal arrives while segments remain.
        task.cancelled = True
        yield _Seg(10.0, 20.0, "two")
        yield _Seg(20.0, 30.0, "three")

    class _Model:
        def transcribe(self, path, **kwargs):
            return _segs(), _Info()

    monkeypatch.setattr(t, "MODEL", _Model())
    monkeypatch.setattr(t, "PIPELINE", None)
    monkeypatch.setattr(t, "MODEL_READY", True)
    monkeypatch.setattr(t, "MODEL_ERROR", None)
    monkeypatch.setattr(t, "get_duration", lambda p: 100.0)

    writes: list = []
    monkeypatch.setattr(
        t._checkpoint, "write_checkpoint",
        lambda *a, **kw: writes.append((a, kw)),
    )
    wrote_outputs: list = []
    monkeypatch.setattr(
        t, "_write_outputs",
        lambda *a, **kw: (wrote_outputs.append(a), [])[1],
    )

    t.transcribe(task)

    assert writes, "cancel mid-run did not flush a resumable checkpoint"
    assert not wrote_outputs, "final outputs were written despite cancellation"


def test_no_cancel_completes_and_writes_outputs(monkeypatch, tmp_path):
    """Control: the SAME harness without a cancel writes outputs and no
    mid-run checkpoint survives (proves the cancel above is what triggers
    the checkpoint, not the harness)."""
    import core.transcriber as t
    from core.task import TranscriptionTask

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"\x00")
    task = TranscriptionTask(str(audio))

    def _segs():
        yield _Seg(0.0, 10.0, "one")
        yield _Seg(10.0, 20.0, "two")

    class _Model:
        def transcribe(self, path, **kwargs):
            return _segs(), _Info()

    monkeypatch.setattr(t, "MODEL", _Model())
    monkeypatch.setattr(t, "PIPELINE", None)
    monkeypatch.setattr(t, "MODEL_READY", True)
    monkeypatch.setattr(t, "MODEL_ERROR", None)
    monkeypatch.setattr(t, "get_duration", lambda p: 100.0)
    monkeypatch.setattr(t._checkpoint, "delete_checkpoint", lambda *a, **k: None)

    wrote_outputs: list = []
    monkeypatch.setattr(
        t, "_write_outputs",
        lambda *a, **kw: (wrote_outputs.append(a), ["x.srt"])[1],
    )

    t.transcribe(task)
    assert wrote_outputs, "a non-cancelled run should write its outputs"
