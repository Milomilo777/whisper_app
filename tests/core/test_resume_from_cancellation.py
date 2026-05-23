"""Tests for resume-from-cancellation / pause / crash.

The transcribe loop writes a JSON checkpoint to
``user_data_dir() / "partials"`` periodically. On cancel the partial
is final-flushed; on success it's deleted; on resume the worker
slices the source from ``last_end_time`` and merges the new segments
onto the captured ones.

These tests mock the WhisperModel + ffmpeg slicer — no real model
load, no real audio decoding. The transcriber module is stubbed
identically to the existing ``test_transcriber_helpers.py`` pattern
so it imports cheaply.
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from pathlib import Path
from typing import Any

import pytest


# --- shared fixtures ---------------------------------------------------------


@pytest.fixture
def transcriber(monkeypatch, tmp_path):
    """Import core.transcriber with WhisperModel stubbed AND with
    user_data_dir redirected into the test's tmp_path so checkpoint
    files don't leak between tests or pollute the real user profile.
    """
    if "core.transcriber" not in sys.modules:
        fake_fw = types.ModuleType("faster_whisper")
        fake_fw.WhisperModel = object  # type: ignore[attr-defined]
        sys.modules.setdefault("faster_whisper", fake_fw)
    import core._checkpoint as cp
    import core.config as cfg
    import core.transcriber as t

    # Redirect user_data_dir for both the config module and the
    # already-imported _checkpoint (which captures the reference at
    # import time).
    monkeypatch.setattr(cfg, "user_data_dir", lambda: tmp_path)
    monkeypatch.setattr(cp, "user_data_dir", lambda: tmp_path)
    return t


class _FakeSegment:
    """Mimic the duck-typed object faster_whisper yields per segment."""

    def __init__(self, start: float, end: float, text: str = "x") -> None:
        self.start = start
        self.end = end
        self.text = text
        self.words: list[Any] = []


class _FakeInfo:
    def __init__(self, language: str = "en", probability: float = 0.9) -> None:
        self.language = language
        self.language_probability = probability


def _install_fake_model(
    transcriber,
    monkeypatch,
    segments: list[_FakeSegment],
    info: _FakeInfo | None = None,
):
    info = info or _FakeInfo()

    class _Model:
        def transcribe(self, audio_path, **kwargs):  # noqa: ARG002
            return (iter(segments), info)

    monkeypatch.setattr(transcriber, "MODEL", _Model())
    monkeypatch.setattr(transcriber, "PIPELINE", None)
    monkeypatch.setattr(transcriber, "MODEL_READY", True)
    monkeypatch.setattr(transcriber, "MODEL_ERROR", None)

    # Bypass the post-pipeline + writers — we're only testing the
    # checkpoint / resume mechanics, not diarisation / output writing.
    monkeypatch.setattr(
        transcriber, "_run_post_pipeline",
        lambda task, segs, lang, log_cb, pcb=None: 0,
    )
    monkeypatch.setattr(
        transcriber, "_write_outputs",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        transcriber, "_write_chapter_sidecar",
        lambda base, chapters: None,
    )
    # get_duration uses ffprobe — stub so we don't need a real audio file.
    monkeypatch.setattr(transcriber, "get_duration", lambda p: 1000.0)


def _make_audio_file(tmp_path: Path, name: str = "fake.wav") -> str:
    p = tmp_path / name
    p.write_bytes(b"\0" * 16)
    return str(p)


# --- 1. checkpoint written during transcribe + deleted on success ------------


def test_checkpoint_written_during_transcribe(transcriber, monkeypatch, tmp_path):
    """After more than N segments the partial JSON must appear on
    disk, then be deleted on normal completion."""
    from core import _checkpoint
    from core.task import TranscriptionTask

    # Lower the cadence so the test finishes quickly: a checkpoint
    # after every 2 segments instead of every 10.
    monkeypatch.setattr(transcriber, "_CHECKPOINT_EVERY_N_SEGMENTS", 2)
    monkeypatch.setattr(transcriber, "_CHECKPOINT_EVERY_N_SECONDS", 9999.0)

    audio = _make_audio_file(tmp_path)
    segs = [_FakeSegment(i * 5.0, (i + 1) * 5.0, f"s{i}") for i in range(5)]
    _install_fake_model(transcriber, monkeypatch, segs)

    # Sanity: capture the path the writer would target, and observe
    # the file appearing mid-run by stubbing _write_outputs to record
    # the checkpoint state at completion-time.
    cp_path = _checkpoint.checkpoint_path(audio)
    seen_during_run: dict[str, bool] = {"present": False}

    def _capture_writes(*a, **kw):  # noqa: ARG001
        seen_during_run["present"] = cp_path.exists()
        return []
    monkeypatch.setattr(transcriber, "_write_outputs", _capture_writes)

    task = TranscriptionTask(audio)
    transcriber.transcribe(task)

    # The checkpoint must have existed during the run (right before
    # the writer ran). On success it's deleted.
    assert seen_during_run["present"], (
        "Expected periodic checkpoint to be on disk during the run"
    )
    assert not cp_path.exists(), (
        f"Checkpoint at {cp_path} should be deleted on success"
    )


# --- 2. checkpoint persists on cancel ----------------------------------------


def test_checkpoint_persists_on_cancel(transcriber, monkeypatch, tmp_path):
    """When task.cancelled flips mid-loop, the partial JSON must
    remain on disk so the user can resume."""
    from core import _checkpoint
    from core.task import TranscriptionTask

    monkeypatch.setattr(transcriber, "_CHECKPOINT_EVERY_N_SEGMENTS", 1)
    monkeypatch.setattr(transcriber, "_CHECKPOINT_EVERY_N_SECONDS", 9999.0)

    audio = _make_audio_file(tmp_path)
    task = TranscriptionTask(audio)

    # Cancel after the 2nd segment. We flip task.cancelled from
    # inside the segment iterator via a generator wrapper.
    raw = [_FakeSegment(i * 5.0, (i + 1) * 5.0, f"s{i}") for i in range(10)]

    def _cancelling_iter():
        for idx, s in enumerate(raw):
            yield s
            if idx == 1:
                task.cancelled = True

    class _Model:
        def transcribe(self, audio_path, **kwargs):  # noqa: ARG002
            return (_cancelling_iter(), _FakeInfo())

    monkeypatch.setattr(transcriber, "MODEL", _Model())
    monkeypatch.setattr(transcriber, "PIPELINE", None)
    monkeypatch.setattr(transcriber, "MODEL_READY", True)
    monkeypatch.setattr(transcriber, "MODEL_ERROR", None)
    monkeypatch.setattr(
        transcriber, "_run_post_pipeline",
        lambda task, segs, lang, log_cb, pcb=None: 0,
    )
    monkeypatch.setattr(transcriber, "_write_outputs", lambda *a, **kw: [])
    monkeypatch.setattr(transcriber, "_write_chapter_sidecar", lambda b, c: None)
    monkeypatch.setattr(transcriber, "get_duration", lambda p: 1000.0)

    transcriber.transcribe(task)

    cp_path = _checkpoint.checkpoint_path(audio)
    assert cp_path.exists(), "Checkpoint should remain on disk after cancel"
    data = json.loads(cp_path.read_text(encoding="utf-8"))
    assert data["segment_count"] >= 2
    assert data["last_end_time"] >= 10.0


# --- 3. resume validation rejects stale source -------------------------------


def test_resume_validation_rejects_stale_source(transcriber, monkeypatch, tmp_path):
    """If the source file's mtime changed after the checkpoint was
    written, resume_transcription must return False and delete the
    stale partial."""
    from core import _checkpoint
    from core.task import TranscriptionTask

    audio = _make_audio_file(tmp_path)
    # Write a checkpoint pinned to the current size + mtime.
    _checkpoint.write_checkpoint(
        audio,
        backend="faster_whisper",
        model_name="faster-whisper-large-v3",
        language="en",
        language_probability=0.9,
        cfg_fingerprint="x",
        last_end_time=10.0,
        segments=[{"start": 0.0, "end": 10.0, "text": "hello"}],
        checkpoint_time=time.time(),
    )

    # Bump the source mtime by writing a different payload.
    time.sleep(0.05)
    Path(audio).write_bytes(b"\0" * 32)

    # Make sure the transcriber doesn't try to slice anything: we
    # expect the resume to bail BEFORE reaching ffmpeg.
    monkeypatch.setattr(
        transcriber, "_slice_audio_from",
        lambda *a, **kw: pytest.fail("slicer should not be called on stale"),
    )

    task = TranscriptionTask(audio)
    result = transcriber.resume_transcription(task)
    assert result is False
    assert not _checkpoint.checkpoint_path(audio).exists()


# --- 4. resume validation rejects changed config -----------------------------


def test_resume_validation_rejects_changed_config(transcriber, monkeypatch, tmp_path):
    """A different config_fingerprint at resume time must fall back
    to a full re-run and drop the partial."""
    from core import _checkpoint
    from core.task import TranscriptionTask

    audio = _make_audio_file(tmp_path)

    # Write the checkpoint with one fingerprint, then change config
    # so the computed fingerprint at resume time differs.
    _checkpoint.write_checkpoint(
        audio,
        backend="faster_whisper",
        model_name=str(transcriber.config.get("model", {}).get("name", "")),
        language="en",
        language_probability=0.9,
        cfg_fingerprint="this-fingerprint-does-not-match-anything-real",
        last_end_time=10.0,
        segments=[{"start": 0.0, "end": 10.0, "text": "hi"}],
        checkpoint_time=time.time(),
    )

    monkeypatch.setattr(
        transcriber, "_slice_audio_from",
        lambda *a, **kw: pytest.fail("slicer should not be called on bad fp"),
    )

    task = TranscriptionTask(audio)
    result = transcriber.resume_transcription(task)
    assert result is False
    assert not _checkpoint.checkpoint_path(audio).exists()


# --- 5. resume offsets segments correctly ------------------------------------


def test_resume_offsets_segments_correctly(transcriber, monkeypatch, tmp_path):
    """Checkpoint with last_end_time=100 + 3 prior segments; mock
    returns 2 new tail segments at 0..5 and 5..12. After resume the
    merged list must have 5 segments with the new ones offset into
    the original timeline (100..105, 105..112)."""
    from core import _checkpoint
    from core.task import TranscriptionTask

    audio = _make_audio_file(tmp_path)
    prior = [
        {"start": 0.0, "end": 40.0, "text": "a"},
        {"start": 40.0, "end": 80.0, "text": "b"},
        {"start": 80.0, "end": 100.0, "text": "c"},
    ]

    # Match the current fingerprint so validation passes.
    fp = _checkpoint.config_fingerprint(transcriber.config)
    model_name = str(transcriber.config.get("model", {}).get("name", "")) \
        or str(transcriber.config.get("whisper_model", ""))
    _checkpoint.write_checkpoint(
        audio,
        backend="faster_whisper",
        model_name=model_name,
        language="en",
        language_probability=0.9,
        cfg_fingerprint=fp,
        last_end_time=100.0,
        segments=prior,
        checkpoint_time=time.time(),
    )

    # Fake the model so it returns two tail segments [0..5, 5..12].
    new_segs = [_FakeSegment(0.0, 5.0, "d"), _FakeSegment(5.0, 12.0, "e")]

    class _Model:
        def transcribe(self, audio_path, **kwargs):  # noqa: ARG002
            return (iter(new_segs), _FakeInfo("en", 0.99))

    monkeypatch.setattr(transcriber, "MODEL", _Model())
    monkeypatch.setattr(transcriber, "PIPELINE", None)
    monkeypatch.setattr(transcriber, "MODEL_READY", True)
    monkeypatch.setattr(transcriber, "MODEL_ERROR", None)
    monkeypatch.setattr(transcriber, "_slice_audio_from",
                        lambda src, st, od: str(tmp_path / "slice.wav"))
    monkeypatch.setattr(
        transcriber, "_run_post_pipeline",
        lambda task, segs, lang, log_cb, pcb=None: 0,
    )

    written_segments: dict[str, list[dict[str, Any]]] = {}

    def _capture_outputs(base, segs, *a, **kw):  # noqa: ARG001
        written_segments["final"] = list(segs)
        return []
    monkeypatch.setattr(transcriber, "_write_outputs", _capture_outputs)
    monkeypatch.setattr(transcriber, "_write_chapter_sidecar", lambda b, c: None)

    # Ensure the slicer's "always cleanup" os.unlink doesn't raise.
    (tmp_path / "slice.wav").write_bytes(b"\0")

    task = TranscriptionTask(audio)
    result = transcriber.resume_transcription(task)
    assert result is True

    final = written_segments["final"]
    assert len(final) == 5, f"expected 5 merged segments, got {len(final)}"
    # First three are the prior, byte-for-byte.
    assert final[0]["text"] == "a" and final[0]["end"] == 40.0
    assert final[2]["end"] == 100.0
    # Last two are the new ones, offset by last_end_time=100.
    assert final[3]["start"] == 100.0
    assert final[3]["end"] == 105.0
    assert final[3]["text"] == "d"
    assert final[4]["start"] == 105.0
    assert final[4]["end"] == 112.0


# --- 6. successful resume deletes the checkpoint ----------------------------


def test_resume_path_deletes_checkpoint_on_success(transcriber, monkeypatch, tmp_path):
    from core import _checkpoint
    from core.task import TranscriptionTask

    audio = _make_audio_file(tmp_path)
    fp = _checkpoint.config_fingerprint(transcriber.config)
    model_name = str(transcriber.config.get("model", {}).get("name", "")) \
        or str(transcriber.config.get("whisper_model", ""))

    _checkpoint.write_checkpoint(
        audio,
        backend="faster_whisper",
        model_name=model_name,
        language="en",
        language_probability=0.9,
        cfg_fingerprint=fp,
        last_end_time=50.0,
        segments=[{"start": 0.0, "end": 50.0, "text": "prior"}],
        checkpoint_time=time.time(),
    )
    assert _checkpoint.checkpoint_path(audio).exists()

    class _Model:
        def transcribe(self, audio_path, **kwargs):  # noqa: ARG002
            return (iter([_FakeSegment(0.0, 3.0, "tail")]), _FakeInfo())

    monkeypatch.setattr(transcriber, "MODEL", _Model())
    monkeypatch.setattr(transcriber, "PIPELINE", None)
    monkeypatch.setattr(transcriber, "MODEL_READY", True)
    monkeypatch.setattr(transcriber, "MODEL_ERROR", None)
    monkeypatch.setattr(transcriber, "_slice_audio_from",
                        lambda src, st, od: str(tmp_path / "slice.wav"))
    monkeypatch.setattr(
        transcriber, "_run_post_pipeline",
        lambda task, segs, lang, log_cb, pcb=None: 0,
    )
    monkeypatch.setattr(transcriber, "_write_outputs", lambda *a, **kw: [])
    monkeypatch.setattr(transcriber, "_write_chapter_sidecar", lambda b, c: None)
    (tmp_path / "slice.wav").write_bytes(b"\0")

    task = TranscriptionTask(audio)
    assert transcriber.resume_transcription(task) is True
    assert not _checkpoint.checkpoint_path(audio).exists()


# --- 7. has_resumable_checkpoint helper -------------------------------------


def test_has_resumable_checkpoint_round_trip(transcriber, tmp_path):
    """Smoke check for the UI helper the right-click menu calls."""
    from core import _checkpoint

    audio = _make_audio_file(tmp_path)
    assert transcriber.has_resumable_checkpoint(audio) is False
    _checkpoint.write_checkpoint(
        audio,
        backend="faster_whisper",
        model_name="x",
        language="en",
        language_probability=0.9,
        cfg_fingerprint="x",
        last_end_time=1.0,
        segments=[],
        checkpoint_time=time.time(),
    )
    assert transcriber.has_resumable_checkpoint(audio) is True
    _checkpoint.delete_checkpoint(audio)
    assert transcriber.has_resumable_checkpoint(audio) is False
