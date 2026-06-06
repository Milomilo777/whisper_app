"""Fixpack regression tests for core.recorder (cluster: recorder).

Covers the DATA-LOSS hole where ``Recorder.stop()`` could truncate /
rewrite the very WAV that a wedged (still-running) capture thread is
still writing — corruption + two writers — and the related ``_wrote_wave``
TOCTOU. All hermetic: no network, no real audio backend, no Tk root.
"""
from __future__ import annotations

import threading
import wave

import pytest

from core import recorder as rec


def _write_frames_wav(path: str, frames: bytes, rate: int = rec.SAMPLE_RATE) -> None:
    """Write a valid mono int16 WAV with ``frames`` payload."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(rec.CHANNELS)
        wf.setsampwidth(rec.SAMPLE_WIDTH_BYTES)
        wf.setframerate(rate)
        wf.writeframes(frames)


def test_stop_does_not_truncate_wav_while_capture_thread_wedged(tmp_path):
    """A wedged capture thread (ignores the stop event past the join
    timeout) still owns the output WAV. ``stop()`` must NOT run the
    truncating ``_finalize_wav`` fallback against that same path — doing
    so corrupts the partial take and creates a second writer.

    On the pre-fix code, stop() saw ``_wrote_wave == False`` and called
    ``_finalize_wav()``, overwriting the streamed frames with a 0-frame
    WAV (DATA LOSS). The fix bails out when the thread is still alive.
    """
    out = tmp_path / "wedged.wav"
    payload = b"\x11\x22" * 4096  # 4096 mono int16 frames already on disk
    _write_frames_wav(str(out), payload)

    r = rec.Recorder(output_path=str(out), mode="mic")

    # Simulate a wedged capture thread: it has already streamed frames to
    # disk (above) but never observes the stop event, so the join times
    # out and the thread is still alive when stop() makes its decision.
    release = threading.Event()

    def _wedged() -> None:
        release.wait(timeout=10.0)

    t = threading.Thread(target=_wedged, daemon=True)
    t.start()
    r._thread = t
    # _wrote_wave stays False because the wedged thread never closed cleanly.
    r._wrote_wave = False

    try:
        returned = r.stop(timeout=0.2)
    finally:
        release.set()
        t.join(timeout=5.0)

    assert returned == str(out)
    # The already-streamed frames must survive untouched — NOT truncated.
    with wave.open(str(out), "rb") as wf:
        assert wf.getnframes() == 4096, "stop() truncated a wedged thread's WAV"


def test_stop_finalizes_when_thread_finished_without_wav(tmp_path):
    """When the capture thread has truly terminated and produced no WAV
    (start failed / instant stop), stop() must still write a valid empty
    WAV so the caller's 'open this file' path never crashes. This is the
    legitimate fallback path the data-loss guard must NOT block."""
    out = tmp_path / "empty.wav"
    r = rec.Recorder(output_path=str(out), mode="mic")

    # A thread that finished immediately (not alive at stop time).
    t = threading.Thread(target=lambda: None, daemon=True)
    t.start()
    t.join(timeout=5.0)
    r._thread = t
    r._wrote_wave = False

    returned = r.stop(timeout=0.2)

    assert returned == str(out)
    assert out.exists()
    with wave.open(str(out), "rb") as wf:
        assert wf.getframerate() == rec.SAMPLE_RATE
        assert wf.getsampwidth() == rec.SAMPLE_WIDTH_BYTES
        assert wf.getnchannels() == rec.CHANNELS
        assert wf.getnframes() == 0


def test_stop_preserves_existing_wav_when_already_wrote(tmp_path):
    """When the loop already produced a WAV (_wrote_wave True and file on
    disk), stop() must NOT rewrite it even though the thread is dead."""
    out = tmp_path / "done.wav"
    payload = b"\x05\x06" * 2048
    _write_frames_wav(str(out), payload)

    r = rec.Recorder(output_path=str(out), mode="mic")
    t = threading.Thread(target=lambda: None, daemon=True)
    t.start()
    t.join(timeout=5.0)
    r._thread = t
    r._wrote_wave = True

    r.stop(timeout=0.2)

    with wave.open(str(out), "rb") as wf:
        assert wf.getnframes() == 2048


def test_stop_with_no_thread_writes_empty_wav(tmp_path):
    """No capture thread ever started (thread is None): the fallback must
    still produce a valid empty WAV (guard keys off liveness, not None)."""
    out = tmp_path / "nostart.wav"
    r = rec.Recorder(output_path=str(out), mode="mic")
    assert r._thread is None

    r.stop(timeout=0.2)

    assert out.exists()
    with wave.open(str(out), "rb") as wf:
        assert wf.getnframes() == 0
