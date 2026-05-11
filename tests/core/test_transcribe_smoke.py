"""Real-audio smoke for ``core.transcriber``.

Loads the smallest tiny.en model into ``user_cache_dir / "models-test"`` and
runs ``transcribe`` on the committed silent_1s.wav. Skipped automatically when:

  - the model can't be downloaded (no network)
  - faster-whisper isn't importable (CI without it)
  - ffmpeg isn't on PATH and the bundled binary is also missing

Coverage of ``core/transcriber.py`` heavy paths comes from this module.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

pytest.importorskip("faster_whisper")

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"
SILENT_WAV = FIXTURES / "silent_1s.wav"
TONE_WAV = FIXTURES / "tone_440hz_2s.wav"


def _have_ffmpeg() -> bool:
    if shutil.which("ffmpeg"):
        return True
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    return candidate.exists()


def _maybe_download_tiny(tmp_root: Path):
    """Try to download tiny.en. Return the loaded WhisperModel or None."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    try:
        return WhisperModel("tiny.en", device="cpu", compute_type="int8",
                            download_root=str(tmp_root))
    except Exception:  # noqa: BLE001
        return None


@pytest.fixture(scope="module")
def tiny_model(tmp_path_factory):
    if not _have_ffmpeg():
        pytest.skip("ffmpeg not available (PATH or bundled bin/)")
    tmp = tmp_path_factory.mktemp("tiny_en_cache")
    model = _maybe_download_tiny(tmp)
    if model is None:
        pytest.skip("Could not download tiny.en (no network?)")
    return model


def _segments_from(model, wav: Path, **kwargs):
    return list(model.transcribe(str(wav), **kwargs)[0])


def test_smoke_silent_returns_with_language(tiny_model):
    segments, info = tiny_model.transcribe(str(SILENT_WAV))
    list(segments)
    assert info.language is not None
    assert isinstance(info.language_probability, (int, float))


def test_vad_suppresses_silence(tiny_model):
    segments = _segments_from(
        tiny_model, SILENT_WAV,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500, "threshold": 0.5,
                        "speech_pad_ms": 400},
    )
    assert len(segments) <= 1


def test_tone_decodes_without_crash(tiny_model):
    segments = _segments_from(tiny_model, TONE_WAV)
    assert isinstance(segments, list)


def test_writers_consume_real_segments(tiny_model):
    segments_iter, _ = tiny_model.transcribe(str(TONE_WAV), word_timestamps=True)
    segments = list(segments_iter)

    from core.writers import get_writer

    payload = [
        {
            "start": float(s.start),
            "end": float(s.end),
            "text": (s.text or "").strip(),
            "words": [
                {"start": float(w.start), "end": float(w.end),
                 "word": w.word or "", "probability": float(w.probability or 0.0)}
                for w in (s.words or [])
            ],
        }
        for s in segments
    ]
    srt_body = get_writer("srt")(payload)
    vtt_body = get_writer("vtt")(payload)
    assert isinstance(srt_body, str)
    assert vtt_body.startswith("WEBVTT")
