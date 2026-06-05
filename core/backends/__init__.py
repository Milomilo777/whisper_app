"""Pluggable Whisper backends.

The transcriber-level dispatcher reads ``config["transcribe_backend"]``
and calls :func:`get_backend` to obtain a :class:`Backend` instance.
Each backend implements load/transcribe/unload against a common
interface so the rest of the pipeline (diarization, writers, queue)
doesn't have to know which model is running underneath.

Currently supported:

  * ``faster_whisper`` (default) — the existing CTranslate2 path.
    Loads ``faster-whisper-large-v3`` from ``config["model_path"]``
    and supports CUDA via ``BatchedInferencePipeline``.

  * ``whisper_cpp`` — pywhispercpp wrapper. Quantised ggml models
    are much smaller (e.g. ``ggml-large-v3-q5_0.bin`` ≈ 1.1 GB) and
    run on weak CPUs that struggle with the float16 faster-whisper
    build. Opt-in via the Advanced dialog.

  * ``parakeet`` — NVIDIA Parakeet TDT v3 via sherpa-onnx. Opt-in.

  * ``cloud_stt`` — OPTIONAL cloud transcription via the Google Gemini
    API (uploads audio to Google; breaks the offline guarantee). Opt-in
    via the Advanced dialog with a pasted API key.
"""
from __future__ import annotations

from .base import Backend, LanguageInfo


def get_backend(name: str) -> Backend:
    """Return a :class:`Backend` instance for ``name``.

    Unknown names silently fall back to ``faster_whisper`` so a
    stale config never blocks the user from transcribing.
    """
    name = (name or "").strip().lower() or "faster_whisper"
    if name == "whisper_cpp":
        from .whisper_cpp import WhisperCppBackend
        return WhisperCppBackend()
    if name == "parakeet":
        from .parakeet import ParakeetBackend
        return ParakeetBackend()
    if name == "cloud_stt":
        from .cloud_stt import CloudSttBackend
        return CloudSttBackend()
    from .faster_whisper_be import FasterWhisperBackend
    return FasterWhisperBackend()


__all__ = ["Backend", "LanguageInfo", "get_backend"]
