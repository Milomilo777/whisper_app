"""Whisper model lifecycle + the transcribe loop.

The basic edition only ever runs faster-whisper. No backend dispatch,
no resume, no diarisation / chapters / alignment / Demucs / LLM. The
loop is intentionally compact (~200 LOC) and easy to audit.

Module-level globals (``MODEL`` / ``MODEL_READY`` / ``MODEL_ERROR``)
are set once per worker process by :func:`load_existing_model` so
each transcribe call reuses the loaded weights.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from faster_whisper import WhisperModel

try:  # 1.0.3+ ships this; older wheels do not.
    from faster_whisper import BatchedInferencePipeline  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    BatchedInferencePipeline = None  # type: ignore[assignment]

from . import hardware as _hw
from .config import load_config
from .paths import bundled_binary
from .task import TranscriptionTask
from .writers import get_writer, supported_formats

logger = logging.getLogger(__name__)

# Module-level config snapshot. Loaded once at import; the worker
# main() refreshes it once after parsing argv if needed. Re-reading
# on every transcribe would double the disk I/O for zero gain in the
# basic edition where the config can't change mid-session.
config: dict[str, Any] = load_config()

MODEL: Any = None
PIPELINE: Any = None  # BatchedInferencePipeline wrapper on CUDA
MODEL_READY: bool = False
MODEL_ERROR: str | None = None


def _log(msg: str, cb: Callable[[str], None] | None) -> None:
    if cb:
        cb(msg)
    else:
        logger.info(msg)


def detect_device() -> tuple[str, str]:
    """Thin wrapper around :func:`core.hardware.detect_device_for`."""
    return _hw.detect_device_for(config)


# Resolved once at import; the worker logs it before the model load.
device, compute_type = detect_device()


def is_model_ready() -> bool:
    return MODEL_READY


def get_model_error() -> str | None:
    return MODEL_ERROR


def _wrap_for_batched(model: Any) -> Any:
    """Wrap with BatchedInferencePipeline on CUDA when available."""
    if device != "cuda" or BatchedInferencePipeline is None:
        return None
    try:
        return BatchedInferencePipeline(model=model)
    except Exception as e:  # noqa: BLE001
        logger.info("BatchedInferencePipeline unavailable: %s", e)
        return None


def load_existing_model(
    status_cb: Callable[[str], None] | None = None,
) -> bool:
    """Load the model from ``config["model_path"]``; populate globals.

    Returns False (and sets :data:`MODEL_ERROR`) if the path is
    missing or :class:`WhisperModel` construction raises. The worker
    main loop then emits ``startup_error`` and exits — the parent
    will spawn the model-download dialog and try again.
    """
    global MODEL, PIPELINE, MODEL_READY, MODEL_ERROR

    MODEL_READY = False
    MODEL_ERROR = None

    model_path = Path(config["model_path"])
    if not model_path.exists():
        MODEL_ERROR = f"Model folder missing: {model_path}"
        if status_cb:
            status_cb(MODEL_ERROR)
        return False

    try:
        if status_cb:
            status_cb("Loading Whisper model...")
        logger.info(
            "model_load model_path=%s device=%s compute_type=%s",
            model_path, device, compute_type,
        )
        MODEL = WhisperModel(
            str(model_path), device=device, compute_type=compute_type,
        )
        PIPELINE = _wrap_for_batched(MODEL)
        MODEL_READY = True
        if status_cb:
            status_cb("Model loaded")
        return True
    except Exception as e:  # noqa: BLE001
        MODEL_ERROR = str(e)
        if status_cb:
            status_cb(f"Model failed to load: {e}")
        return False


def _vad_parameters() -> dict[str, Any] | None:
    """Default VAD knobs — same values the full-fat repo ships with."""
    if not config.get("vad_enabled", True):
        return None
    return {
        "min_silence_duration_ms": 500,
        "threshold": 0.5,
        "speech_pad_ms": 400,
    }


def _segment_to_dict(seg: Any) -> dict[str, Any]:
    """Reduce a faster-whisper segment to the JSON-friendly subset
    the writers consume.
    """
    return {
        "start": float(seg.start),
        "end": float(seg.end),
        "text": (seg.text or "").strip(),
    }


def get_duration(path: str) -> float:
    """Call bundled ffprobe to read the container duration in seconds."""
    ffprobe = bundled_binary("ffprobe")
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 60,
    }
    if os.name == "nt":
        # Without CREATE_NO_WINDOW, ffprobe pops a black console
        # window on every transcribe under the windowed exe.
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            **kwargs,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ffprobe timed out for {path}") from e
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(
            f"ffprobe failed (exit={r.returncode}) for {path}: "
            f"{r.stderr.strip() or 'no output'}"
        )
    return float(r.stdout.strip())


def _fmt(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02}:{m:02}:{s:02}"


def _build_transcribe_kwargs(task: TranscriptionTask) -> dict[str, Any]:
    """Assemble the kwargs for ``WhisperModel.transcribe``."""
    kwargs: dict[str, Any] = {
        "vad_filter": _vad_parameters() is not None,
        # word_timestamps off in basic — the SRT/JSON/TXT writers
        # don't need word-level detail and disabling it ~halves the
        # CPU work on long files.
        "word_timestamps": False,
    }
    if kwargs["vad_filter"]:
        kwargs["vad_parameters"] = _vad_parameters()
    forced_lang = getattr(task, "language", None)
    if forced_lang and forced_lang != "auto":
        kwargs["language"] = forced_lang
    return kwargs


def _write_outputs(
    base: str,
    segments_data: list[dict[str, Any]],
    audio_path: str,
) -> list[str]:
    """Write each requested format atomically (write to .part, rename).

    A mid-write crash leaves either the previous (intact) file or
    nothing — never a half-written SRT some downstream tool will
    silently mis-parse.
    """
    formats = list(config.get("output_formats") or ["srt", "json", "txt"])
    written: list[str] = []
    available = supported_formats()
    requested_known = [f for f in formats if f in available]
    if formats and not requested_known:
        raise RuntimeError(
            f"None of the requested output formats are known: "
            f"{formats!r}. Supported: {sorted(available)!r}."
        )
    for fmt_name in formats:
        if fmt_name not in available:
            continue
        ext = "json" if fmt_name == "json" else fmt_name
        path = f"{base}.{ext}"
        part_path = f"{path}.{os.getpid()}-{threading.get_ident()}.part"
        try:
            payload = get_writer(fmt_name)(segments_data, audio_path)
            with open(part_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload)
            os.replace(part_path, path)
        except Exception:
            try:
                os.unlink(part_path)
            except OSError:
                pass
            # Roll back any files we already wrote during this batch.
            for prior in written:
                try:
                    os.unlink(prior)
                except OSError:
                    pass
            raise
        written.append(path)
    return written


def transcribe(
    task: TranscriptionTask,
    progress_cb: Callable[[int], None] | None = None,
    log_cb: Callable[[str], None] | None = None,
    language_cb: Callable[[str, float], None] | None = None,
) -> None:
    """Transcribe one file and write the configured output formats.

    Blocks until the model is :data:`MODEL_READY`. Raises
    :class:`RuntimeError` if model loading failed permanently.
    Co-operatively cancels via ``task.cancelled``.
    """
    global MODEL
    while not MODEL_READY:
        if MODEL_ERROR:
            raise RuntimeError(MODEL_ERROR)
        time.sleep(0.5)

    audio_path = task.file_path
    duration = get_duration(audio_path)
    start = time.time()
    _log(f"Processing: {audio_path}", log_cb)

    assert MODEL is not None
    transcribe_kwargs = _build_transcribe_kwargs(task)
    runner = PIPELINE if PIPELINE is not None else MODEL

    segments, info = runner.transcribe(audio_path, **transcribe_kwargs)

    if getattr(info, "language", None):
        lang_code = str(info.language)
        lang_prob = float(getattr(info, "language_probability", 0.0))
        if lang_prob < 0.5:
            _log(
                f"WARN: detected language={lang_code} with low confidence "
                f"({lang_prob:.0%}). The output language tag may be wrong.",
                log_cb,
            )
        if language_cb:
            try:
                language_cb(lang_code, lang_prob)
            except Exception:
                logger.exception("language_cb raised")
        task.detected_language = lang_code
        task.language_probability = lang_prob

    base = os.path.splitext(task.file_path)[0]
    segments_data: list[dict[str, Any]] = []
    for seg in segments:
        if task.cancelled:
            _log("Task cancelled", log_cb)
            return
        percent = min(100, int((seg.end / duration) * 100)) if duration else 0
        _log(
            f"[{percent}%] {_fmt(seg.start)} --> {_fmt(seg.end)} | "
            f"{(seg.text or '').strip()}",
            log_cb,
        )
        if progress_cb:
            progress_cb(percent)
        segments_data.append(_segment_to_dict(seg))

    written = _write_outputs(base, segments_data, task.file_path)
    _log(
        f"Wrote {len(written)} output file(s): "
        f"{', '.join(os.path.basename(p) for p in written)}",
        log_cb,
    )
    if progress_cb:
        progress_cb(100)
    _log(f"Done in {time.time() - start:.2f}s", log_cb)
