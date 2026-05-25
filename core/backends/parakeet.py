"""Parakeet TDT v3 backend via sherpa-onnx (v0.8 Phase 3).

NVIDIA's `parakeet-tdt-0.6b-v3` is ~5× faster than Whisper Large
v3 Turbo on European languages and ships an ONNX export that runs
on CPU, CUDA, DirectML, and OpenVINO via the sherpa-onnx
execution-provider stack.

Why a separate backend instead of bolting it onto faster_whisper:

  * Different tokenizer + decoding format (RNN-T / TDT, not the
    Whisper attention decoder).
  * Different model file layout — three .onnx files + tokens.txt,
    not a single CTranslate2 directory.
  * sherpa_onnx is already bundled (Phase-1 diarisation already
    depends on it), so adding the Parakeet adapter has zero new
    wheel cost.

Model file layout under ``user_cache_dir() / "parakeet"``::

    encoder.onnx
    decoder.onnx
    joiner.onnx
    tokens.txt

The user installs them via "Download Parakeet model…" in the
Advanced dialog (future work) or drops them in manually. The
backend reports :func:`is_available` based on the file presence
+ sherpa_onnx importability.

Language detection: Parakeet doesn't ship language ID — we mark
``LanguageInfo.language = ""`` so downstream code (filename
template, viewer) handles "no language" gracefully (already
exercised by the alt-backend path).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .._liveness_tick import liveness_tick
from ..config import user_cache_dir
from .base import Backend, LanguageInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- model files


MODEL_DIR_NAME = "parakeet"
REQUIRED_FILES: tuple[str, ...] = (
    "encoder.onnx",
    "decoder.onnx",
    "joiner.onnx",
    "tokens.txt",
)


def model_dir() -> Path:
    return user_cache_dir() / MODEL_DIR_NAME


def is_model_present(directory: Path | None = None) -> bool:
    """True iff all four required files exist in the model dir."""
    d = directory if directory is not None else model_dir()
    return all((d / name).exists() for name in REQUIRED_FILES)


def runtime_available() -> bool:
    """True iff sherpa_onnx imports cleanly."""
    try:
        import sherpa_onnx  # type: ignore[import-not-found] # noqa: F401
    except Exception:  # noqa: BLE001 — a wrong-arch / missing native DLL
        # raises OSError/RuntimeError at import, not ImportError (the VLC
        # bug class); a probe must degrade to "unavailable", never crash.
        return False
    return True


def availability_reason() -> str:
    if not runtime_available():
        return "sherpa-onnx not installed."
    if not is_model_present():
        missing = [
            name for name in REQUIRED_FILES
            if not (model_dir() / name).exists()
        ]
        return (
            f"Parakeet model files missing under {model_dir()}: "
            f"{', '.join(missing)}"
        )
    return ""


# ---------------------------------------------------------------- backend


class ParakeetBackend(Backend):
    """sherpa-onnx OfflineRecognizer wrapper."""

    name = "parakeet"

    def __init__(self) -> None:
        self._recognizer: Any = None
        self._error: str | None = None
        self._lock = threading.Lock()

    def load(
        self,
        status_cb: Callable[[str], None] | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> bool:
        if self._recognizer is not None:
            return True
        if not runtime_available():
            self._error = availability_reason()
            return False
        if not is_model_present():
            self._error = availability_reason()
            return False
        if status_cb:
            status_cb("Loading Parakeet model…")
        try:
            import sherpa_onnx  # type: ignore[import-not-found]
            d = model_dir()
            cfg = sherpa_onnx.OfflineRecognizerConfig(  # type: ignore[attr-defined]
                feat_config=sherpa_onnx.FeatureExtractorConfig(  # type: ignore[attr-defined]
                    sampling_rate=16000,
                    feature_dim=80,
                ),
                model_config=sherpa_onnx.OfflineModelConfig(  # type: ignore[attr-defined]
                    transducer=sherpa_onnx.OfflineTransducerModelConfig(  # type: ignore[attr-defined]
                        encoder=str(d / "encoder.onnx"),
                        decoder=str(d / "decoder.onnx"),
                        joiner=str(d / "joiner.onnx"),
                    ),
                    tokens=str(d / "tokens.txt"),
                    num_threads=2,
                    debug=False,
                ),
                decoding_method="greedy_search",
            )
            self._recognizer = sherpa_onnx.OfflineRecognizer(cfg)  # type: ignore[attr-defined]
            if status_cb:
                status_cb("Parakeet model loaded")
            return True
        except Exception as e:  # noqa: BLE001
            self._error = f"Parakeet load failed: {e}"
            logger.exception("Parakeet load failed")
            return False

    def is_ready(self) -> bool:
        return self._recognizer is not None

    def get_error(self) -> str | None:
        return self._error

    def transcribe_to_segments(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        want_words: bool = False,
        vad_parameters: dict[str, Any] | None = None,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
        batch_size: int = 16,
        progress_cb: Callable[[int], None] | None = None,
        log_cb: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        paused: Callable[[], bool] | None = None,
        duration: float = 0.0,
    ) -> tuple[list[dict[str, Any]], LanguageInfo]:
        """Transcribe one audio file via the Parakeet recogniser.

        Parakeet emits one stream per file (offline mode). We pass
        a 16 kHz mono float32 array; the decoder yields tokens +
        their timestamps which we convert into Whisper-shaped
        segment dicts so the writers / viewer don't care which
        backend produced them.
        """
        with self._lock:
            if not self.is_ready() and not self.load(log_cb):
                raise RuntimeError(self._error or "Parakeet backend not ready")

            samples, sample_rate = _load_audio_as_float32(audio_path)
            assert self._recognizer is not None
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            # ``decode_stream`` is a single C-level call that processes
            # the whole file with the GIL held and emits no progress.
            # Wrap it in a liveness tick so the parent watchdog sees
            # a heartbeat at least every 10 s on slow CPUs.
            with liveness_tick(log_cb, "Parakeet decode"):
                self._recognizer.decode_stream(stream)

            result = stream.result
            text = (getattr(result, "text", "") or "").strip()
            tokens = list(getattr(result, "tokens", []) or [])
            timestamps = list(getattr(result, "timestamps", []) or [])

        segments = _tokens_to_segments(text, tokens, timestamps, duration)
        if progress_cb:
            progress_cb(100)
        if log_cb:
            log_cb(f"Parakeet: {len(segments)} segment(s) decoded.")
        return segments, LanguageInfo(language="", probability=0.0)


# ---------------------------------------------------------------- helpers


def _load_audio_as_float32(audio_path: str) -> tuple[Any, int]:
    """Load any audio file as mono float32 @ 16 kHz.

    We re-use the bundled ffmpeg to decode (any format) and pipe
    raw s16le samples back via subprocess. Mirrors the existing
    transcriber path so Parakeet supports the same formats as the
    Whisper backend without an extra audio-library dep.
    """
    import os
    import subprocess
    import numpy as np
    from ..paths import bundled_binary

    ffmpeg = bundled_binary("ffmpeg")
    cmd = [
        ffmpeg, "-nostdin", "-loglevel", "error",
        "-i", audio_path,
        "-f", "s16le", "-ac", "1", "-ar", "16000", "-",
    ]
    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "check": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, **kwargs)
    except (FileNotFoundError, OSError) as e:
        # bundled_binary falls back to the bare "ffmpeg" name when the
        # binary isn't in the frozen bin/ tree; without ffmpeg this raises
        # before check= fires. Surface a clean error instead of crashing
        # the worker with a raw traceback.
        raise RuntimeError(
            "ffmpeg is required to decode audio for the Parakeet backend "
            "but was not found. Use the default engine, or install ffmpeg."
        ) from e
    arr = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return arr, 16000


@dataclass
class _SegmentInProgress:
    text_parts: list[str]
    start: float
    end: float


def _tokens_to_segments(
    text: str,
    tokens: list[str],
    timestamps: list[float],
    duration: float,
    *,
    max_gap_seconds: float = 0.8,
) -> list[dict[str, Any]]:
    """Group Parakeet tokens into Whisper-shaped segments.

    Parakeet returns a flat token stream; the writers expect
    sentence-shaped segments. We break a new segment whenever the
    gap between consecutive token timestamps exceeds
    ``max_gap_seconds`` (≈ a sentence pause), or when a token
    contains terminal punctuation.
    """
    if not text:
        return []
    if not tokens or not timestamps:
        # Fall back to a single whole-file segment when timestamps
        # weren't emitted (e.g. older sherpa_onnx versions).
        return [{
            "start": 0.0,
            "end": float(duration or 0.0),
            "text": text.strip(),
        }]

    pairs = list(zip(tokens, timestamps))
    segments: list[_SegmentInProgress] = []
    current = _SegmentInProgress(text_parts=[], start=float(pairs[0][1]), end=float(pairs[0][1]))
    prev_t = float(pairs[0][1])
    for tok, t in pairs:
        t_f = float(t)
        gap = t_f - prev_t
        if gap > max_gap_seconds and current.text_parts:
            segments.append(current)
            current = _SegmentInProgress(text_parts=[tok], start=t_f, end=t_f)
        else:
            current.text_parts.append(tok)
            current.end = t_f
        prev_t = t_f
    if current.text_parts:
        segments.append(current)

    out: list[dict[str, Any]] = []
    for seg in segments:
        out.append({
            "start": float(seg.start),
            "end": float(seg.end),
            "text": "".join(seg.text_parts).strip(),
        })
    return out
