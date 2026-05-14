"""Whisper model lifecycle + the transcribe loop.

The module keeps a single ``MODEL`` global so worker subprocesses don't load
twice. Phase 2a additions:

* VAD via ``vad_filter=True`` (default ON), tunable via config keys
* Word-level timestamps when ``word_timestamps`` is True
* Language detection captured from ``info.language`` / ``info.language_probability``
  and posted via ``language_cb``
* Multi-format output through :mod:`core.writers`
* :class:`faster_whisper.BatchedInferencePipeline` on CUDA
* Optional ``initial_prompt`` and ``hotwords`` (forwarded if supported)
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

try:  # 1.0.3+ ships this; older wheels do not
    from faster_whisper import BatchedInferencePipeline  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    BatchedInferencePipeline = None  # type: ignore[assignment]

from .config import load_config
from .model_manager import DownloadCancelled, ensure_model
from .task import TranscriptionTask
from .writers import get_writer, supported_formats

logger = logging.getLogger(__name__)

config = load_config()

MODEL: Any = None
PIPELINE: Any = None  # BatchedInferencePipeline wrapper when device == "cuda"
MODEL_READY = False
MODEL_ERROR: str | None = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = PROJECT_ROOT / "bin"


def bundled_binary(name: str) -> str:
    exe = f"{name}.exe" if os.name == "nt" else name
    candidate = BIN_DIR / exe
    return str(candidate) if candidate.exists() else name


def log(msg: str, cb: Callable[[str], None] | None = None) -> None:
    if cb:
        cb(msg)
    else:
        logger.info(msg)


def detect_device() -> tuple[str, str]:
    """Pick (device, compute_type). Honours an explicit ``device`` setting."""
    if config.get("device") != "auto":
        return config.get("device", "cpu"), config.get("compute_type", "int8")
    try:
        import ctranslate2
        if ctranslate2.contains_cuda_device():  # type: ignore[attr-defined]
            supported = set(ctranslate2.get_supported_compute_types("cuda"))
            for ct in ("float16", "int8_float16", "int8"):
                if ct in supported:
                    return "cuda", ct
    except (ImportError, AttributeError, RuntimeError):
        pass
    try:
        import torch  # type: ignore[import-not-found]
        if torch.cuda.is_available():
            return "cuda", "float16"
    except (ImportError, AttributeError):
        pass
    return "cpu", config.get("compute_type", "int8")


device, compute_type = detect_device()


def is_model_ready() -> bool:
    return MODEL_READY


def get_model_error() -> str | None:
    return MODEL_ERROR


def _wrap_for_batched(model: Any) -> Any:
    """Wrap with BatchedInferencePipeline on CUDA if available."""
    if device != "cuda" or BatchedInferencePipeline is None:
        return None
    try:
        return BatchedInferencePipeline(model=model)
    except Exception as e:  # noqa: BLE001
        logger.info("BatchedInferencePipeline unavailable: %s", e)
        return None


def load_existing_model(status_cb: Callable[[str], None] | None = None) -> bool:
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
            status_cb("Loading existing Whisper model...")
        MODEL = WhisperModel(str(model_path), device=device, compute_type=compute_type)
        PIPELINE = _wrap_for_batched(MODEL)
        MODEL_READY = True
        if status_cb:
            status_cb("Model loaded")
        return True
    except Exception as e:
        MODEL_ERROR = str(e)
        if status_cb:
            status_cb(f"Existing model failed to load: {e}")
        return False


def load_model(
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    global MODEL, PIPELINE, MODEL_READY, MODEL_ERROR
    MODEL_READY = False
    MODEL_ERROR = None
    try:
        model_path = ensure_model(config, status_cb, progress_cb, cancel_event)
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Model download cancelled")
        if status_cb:
            status_cb("Loading Whisper model...")
        if progress_cb:
            progress_cb({"phase": "load", "status": "Loading Whisper model...",
                         "percent": 100, "detail": "Preparing model for transcription"})
        MODEL = WhisperModel(model_path, device=device, compute_type=compute_type)
        PIPELINE = _wrap_for_batched(MODEL)
        MODEL_READY = True
        if status_cb:
            status_cb("Model loaded")
        if progress_cb:
            progress_cb({"phase": "loaded", "status": "Model loaded",
                         "percent": 100, "detail": "Ready"})
        return True
    except DownloadCancelled as e:
        MODEL_ERROR = None
        if status_cb:
            status_cb(str(e))
        return False
    except Exception as e:
        MODEL_ERROR = str(e)
        if status_cb:
            status_cb(f"ERROR: {e}")
        raise


def load_model_async(
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    try:
        load_model(status_cb, progress_cb, cancel_event)
    except Exception as e:  # noqa: BLE001
        # Don't propagate (background thread); but logging matters —
        # silently swallowing this hid a real model-corruption case for a
        # whole session in the field.
        logger.exception("Async model load failed: %s", e)
        if status_cb:
            try:
                status_cb(f"ERROR: {e}")
            except Exception:  # noqa: BLE001
                pass


def start_background_model_load(status_cb: Callable[[str], None] | None = None) -> None:
    threading.Thread(target=load_model_async, args=(status_cb,), daemon=True).start()


def get_duration(path: str) -> float:
    ffprobe = bundled_binary("ffprobe")
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(
            f"ffprobe failed (exit={r.returncode}) for {path}: "
            f"{r.stderr.strip() or 'no output'}"
        )
    return float(r.stdout.strip())


def fmt(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02}:{m:02}:{s:02}"


def _vad_parameters() -> dict[str, Any] | None:
    """Build the VAD options dict from config — None when VAD disabled."""
    if not config.get("vad_enabled", True):
        return None
    return {
        "min_silence_duration_ms": int(config.get("vad_min_silence_ms", 500)),
        "threshold": float(config.get("vad_threshold", 0.5)),
        "speech_pad_ms": int(config.get("vad_speech_pad_ms", 400)),
    }


def _segment_to_dict(seg: Any, want_words: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "start": float(seg.start),
        "end": float(seg.end),
        "text": (seg.text or "").strip(),
    }
    if want_words:
        words = getattr(seg, "words", None) or []
        payload["words"] = [
            {
                "start": float(w.start),
                "end": float(w.end),
                "word": (w.word or "").strip(),
                "probability": float(getattr(w, "probability", 0.0)),
            }
            for w in words
        ]
    return payload


def _write_outputs(
    base: str,
    segments_data: list[dict[str, Any]],
    audio_path: str,
    formats: list[str] | None = None,
) -> list[str]:
    formats = formats or list(config.get("output_formats") or ["srt", "json"])
    written: list[str] = []
    available = supported_formats()
    for fmt_name in formats:
        if fmt_name not in available:
            continue
        ext = "json" if fmt_name == "json" else fmt_name
        path = f"{base}.{ext}"
        body = get_writer(fmt_name)(segments_data, audio_path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        written.append(path)
    return written


def transcribe(
    task: TranscriptionTask,
    progress_cb: Callable[[int], None] | None = None,
    log_cb: Callable[[str], None] | None = None,
    language_cb: Callable[[str, float], None] | None = None,
) -> None:
    global MODEL
    while not MODEL_READY:
        if MODEL_ERROR:
            raise RuntimeError(MODEL_ERROR)
        time.sleep(0.5)

    duration = get_duration(task.file_path)
    start = time.time()
    log(f"Processing: {task.file_path}", log_cb)

    assert MODEL is not None
    want_words = bool(config.get("word_timestamps", False))

    transcribe_kwargs: dict[str, Any] = {
        "vad_filter": _vad_parameters() is not None,
        "word_timestamps": want_words,
    }
    if transcribe_kwargs["vad_filter"]:
        transcribe_kwargs["vad_parameters"] = _vad_parameters()

    forced_lang = getattr(task, "language", None)
    if forced_lang:
        transcribe_kwargs["language"] = forced_lang
    initial_prompt = config.get("initial_prompt") or None
    if initial_prompt:
        transcribe_kwargs["initial_prompt"] = initial_prompt
    hotwords = config.get("hotwords") or None
    if hotwords:
        transcribe_kwargs["hotwords"] = hotwords

    runner = PIPELINE if PIPELINE is not None else MODEL
    if PIPELINE is not None:
        transcribe_kwargs["batch_size"] = int(config.get("batch_size", 16))

    segments, info = runner.transcribe(task.file_path, **transcribe_kwargs)

    if language_cb and getattr(info, "language", None):
        try:
            language_cb(str(info.language), float(getattr(info, "language_probability", 0.0)))
        except Exception:  # noqa: BLE001
            pass
    if hasattr(task, "detected_language") and getattr(info, "language", None):
        task.detected_language = str(info.language)
        task.language_probability = float(getattr(info, "language_probability", 0.0))

    base = os.path.splitext(task.file_path)[0]

    segments_data: list[dict[str, Any]] = []
    for seg in segments:
        if task.cancelled:
            log("Task cancelled", log_cb)
            return
        while task.paused and not task.cancelled:
            time.sleep(0.2)

        percent = min(100, int((seg.end / duration) * 100)) if duration else 0
        msg = f"[{percent}%] {fmt(seg.start)} --> {fmt(seg.end)} | {(seg.text or '').strip()}"
        log(msg, log_cb)

        if progress_cb:
            progress_cb(percent)

        segments_data.append(_segment_to_dict(seg, want_words))

    written = _write_outputs(base, segments_data, task.file_path)
    log(f"Wrote {len(written)} output file(s): {', '.join(os.path.basename(p) for p in written)}",
        log_cb)

    if progress_cb:
        progress_cb(100)

    elapsed = time.time() - start
    log(f"Done in {elapsed:.2f}s", log_cb)
