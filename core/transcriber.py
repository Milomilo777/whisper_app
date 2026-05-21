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
from .paths import bundled_binary
from .task import TranscriptionTask
from .writers import get_binary_writer, get_writer, is_binary, supported_formats

logger = logging.getLogger(__name__)

config = load_config()

MODEL: Any = None
PIPELINE: Any = None  # BatchedInferencePipeline wrapper when device == "cuda"
MODEL_READY = False
MODEL_ERROR: str | None = None

# Pluggable backend instance for non-default engines (e.g. whisper.cpp).
# The default faster_whisper path keeps using MODEL/PIPELINE globals so
# every existing test that monkeypatches transcriber.config keeps
# working. Backends other than faster_whisper are routed via
# _ALT_BACKEND when ``config["transcribe_backend"]`` is set.
_ALT_BACKEND: Any = None
_ALT_BACKEND_NAME: str = ""


def log(msg: str, cb: Callable[[str], None] | None = None) -> None:
    if cb:
        cb(msg)
    else:
        logger.info(msg)


def detect_device() -> tuple[str, str]:
    """Pick (device, compute_type).

    Resolution order:
      1. Explicit ``device`` config setting (anything ≠ ``"auto"``).
      2. The Hardware Wizard's persisted choice in ``hardware.json``
         when it picks a tier the bundled backend can drive AND the
         hardware is still present (v0.8).
      3. ctranslate2 CUDA probe.
      4. torch CUDA probe (legacy fallback).
      5. CPU with the configured compute_type.
    """
    if config.get("device") != "auto":
        return config.get("device", "cpu"), config.get("compute_type", "int8")
    try:
        from . import hardware as _hw
        wizard_choice = _hw.device_choice_from_hardware_file()
        if wizard_choice is not None:
            return wizard_choice
    except Exception:  # noqa: BLE001
        pass
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
    """Load the model for the configured backend.

    For the default faster_whisper backend, this populates the legacy
    module-level ``MODEL`` / ``PIPELINE`` globals so the rest of the
    code (and the unit tests) keep working. For non-default backends
    it loads via the backend interface and flips ``MODEL_READY`` so
    the transcribe loop's "wait until ready" check passes.
    """
    global MODEL, PIPELINE, MODEL_READY, MODEL_ERROR, _ALT_BACKEND, _ALT_BACKEND_NAME

    backend_name = (
        str(config.get("transcribe_backend") or "faster_whisper").strip().lower()
    )
    MODEL_READY = False
    MODEL_ERROR = None

    if backend_name and backend_name != "faster_whisper":
        try:
            from .backends import get_backend
            backend = get_backend(backend_name)
        except Exception as e:  # noqa: BLE001
            MODEL_ERROR = f"Backend {backend_name} not available: {e}"
            if status_cb:
                status_cb(MODEL_ERROR)
            return False
        ok = False
        try:
            ok = backend.load(status_cb)
        except Exception as e:  # noqa: BLE001
            MODEL_ERROR = f"{backend_name} load failed: {e}"
            if status_cb:
                status_cb(MODEL_ERROR)
            return False
        if not ok:
            MODEL_ERROR = backend.get_error() or f"{backend_name} load returned False"
            if status_cb:
                status_cb(MODEL_ERROR)
            return False
        _ALT_BACKEND = backend
        _ALT_BACKEND_NAME = backend_name
        MODEL_READY = True
        if status_cb:
            status_cb("Model loaded")
        return True

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
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        # If the user feeds in something pathological (broken container,
        # network mount that stalls), don't block transcription forever.
        "timeout": 60,
    }
    if os.name == "nt":
        # Without this, ffprobe pops a black console window every time the
        # transcriber starts a new file. Invisible in dev (we run from a
        # terminal); user-visible from the windowed exe.
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


def _render_filename_template(
    template: str,
    *,
    base: str,
    ext: str,
    lang: str = "",
    speaker_count: int = 0,
    date: str | None = None,
) -> str:
    """Expand the ``output_filename_template`` config string.

    Tokens supported: ``{base}``, ``{ext}``, ``{lang}``, ``{date}``,
    ``{speaker_count}``. Missing tokens silently render as empty. Any
    other ``{name}`` token is preserved verbatim so a typo doesn't
    yield a confusing FileNotFound at write time.

    Safety:
      * Positional ``{0}`` (or any IndexError-raising shape) falls
        back to the legacy ``"{base}.{ext}"`` layout.
      * Malformed templates (unbalanced braces, attribute access)
        fall back to the legacy layout — a corrupt config never
        blocks a write.
      * Path-traversal is rejected after render: the resolved
        absolute path must stay under the directory of ``base``.
        ``../etc/passwd.srt`` and similar escapes fall back to the
        legacy layout.

    ``base`` is the input-file stem *with* its directory prefix. That
    keeps writes next to the source media by default; the user can
    still pull files into a sibling folder by prefixing with e.g.
    ``"transcripts/{base}.{ext}"`` — split paths are honoured by the
    later ``os.makedirs(dirname, exist_ok=True)``.
    """
    import datetime as _dt

    fields: dict[str, str] = {
        "base": base,
        "ext": ext,
        "lang": (lang or "").strip(),
        "speaker_count": str(int(speaker_count)) if speaker_count else "",
        "date": date if date is not None else _dt.date.today().isoformat(),
    }

    class _Fmt(dict):
        def __missing__(self, key: str) -> str:
            # Preserve unknown tokens verbatim so the user can see the
            # typo rather than getting a silent ENOENT.
            return "{" + key + "}"

    legacy = f"{base}.{ext}"
    try:
        rendered = template.format_map(_Fmt(fields))
    except (IndexError, KeyError, ValueError, TypeError, AttributeError):
        # Malformed template (unbalanced braces, positional `{0}`,
        # attribute access in a token, etc.). Fall back to the safe
        # legacy layout so a corrupt config never blocks a write.
        return legacy

    # Path-traversal guard. ``base`` always has a directory prefix
    # (the source media's folder); a rendered path that resolves
    # outside that root means the template tried to escape via
    # ``../`` segments. Reject and fall back rather than write into
    # an unintended location.
    try:
        base_dir = os.path.dirname(os.path.abspath(base)) or os.path.abspath(".")
        rendered_abs = os.path.abspath(rendered)
        # On Windows os.path.commonpath rejects mixed-drive args; in
        # that case the template is clearly escaping (different drive
        # letter than base) — fall back.
        try:
            common = os.path.commonpath([base_dir, rendered_abs])
        except ValueError:
            return legacy
        if os.path.normcase(common) != os.path.normcase(base_dir):
            return legacy
    except (OSError, ValueError):
        return legacy

    return rendered


def _write_outputs(
    base: str,
    segments_data: list[dict[str, Any]],
    audio_path: str,
    formats: list[str] | None = None,
    *,
    lang: str = "",
    speaker_count: int = 0,
) -> list[str]:
    """Write each requested format atomically.

    Each writer runs to a ``<path>.part`` first, then os.replace's onto
    the final name. If anything raises mid-write — disk full, encoding
    crash, the process dying — the user is left with either the
    previous (intact) version of the file or nothing, never a half-
    written SRT that some downstream tool will reject. The .part file
    is cleaned up on the raise path.

    Text formats go through ``open(..., "w", encoding="utf-8")``;
    binary formats (``docx``) go through ``open(..., "wb")`` with
    bytes payload from ``get_binary_writer``.

    The final path is composed by expanding the
    ``output_filename_template`` config key (default ``"{base}.{ext}"``).
    """
    formats = formats or list(config.get("output_formats") or ["srt", "json"])
    template = str(config.get("output_filename_template") or "{base}.{ext}")
    written: list[str] = []
    available = supported_formats()
    for fmt_name in formats:
        if fmt_name not in available:
            continue
        ext = "json" if fmt_name == "json" else fmt_name
        path = _render_filename_template(
            template,
            base=base,
            ext=ext,
            lang=lang,
            speaker_count=speaker_count,
        )
        # Honour template-supplied subdirectories. Defensive: only
        # makedirs when the dirname is non-empty and differs from the
        # source folder we're already writing into.
        out_dir = os.path.dirname(path)
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError:
                pass
        # Unique .part suffix per pid + thread so two parallel
        # workers transcribing the SAME source file don't race-write
        # to the same .part path (Windows treats the second open as
        # PermissionError because the first writer still holds the
        # handle). os.replace onto the final path remains atomic;
        # the last writer wins for the final file, which matches the
        # POSIX "last writer wins" semantic that callers already
        # expect for redundant parallel transcriptions.
        part_path = (
            f"{path}.{os.getpid()}-{threading.get_ident()}.part"
        )
        try:
            if is_binary(fmt_name):
                payload_b = get_binary_writer(fmt_name)(segments_data, audio_path)
                with open(part_path, "wb") as fb:
                    fb.write(payload_b)
            else:
                payload_s = get_writer(fmt_name)(segments_data, audio_path)
                with open(part_path, "w", encoding="utf-8", newline="\n") as fs:
                    fs.write(payload_s)
            os.replace(part_path, path)
        except Exception:
            try:
                os.unlink(part_path)
            except OSError:
                pass
            # Clean up any files we already wrote on the way to this
            # failure — disk-full mid-batch used to leave the user
            # with a mix of fresh + stale files. Roll those back so
            # the final state matches the pre-call state.
            for prior in written:
                try:
                    os.unlink(prior)
                except OSError:
                    pass
            raise
        written.append(path)
    return written


_ALT_BACKEND_LOCK = threading.Lock()


def _deep_merge_dict(dest: dict[str, Any], src: dict[str, Any]) -> None:
    """Recursively merge ``src`` into ``dest`` in place.

    Unlike ``dict.update``, nested dicts are walked depth-first so a
    user override of `{"model": {"name": "tiny"}}` keeps any other
    keys under ``model`` (e.g. ``url``, ``md5``) intact.
    """
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dest.get(k), dict):
            _deep_merge_dict(dest[k], v)
        else:
            dest[k] = v


def _get_alt_backend(name: str) -> Any:
    """Lazy-construct (and load) the alt backend for ``name``.

    Worker processes only need one backend per run, so we cache the
    instance here. The Advanced dialog's "Download model..." button is
    expected to have populated the model file before the user picks
    the matching backend in config.

    Thread-safe: guarded by ``_ALT_BACKEND_LOCK`` so two concurrent
    ``transcribe()`` calls don't both load (and one overwrite the
    other) on first use.
    """
    global _ALT_BACKEND, _ALT_BACKEND_NAME
    with _ALT_BACKEND_LOCK:
        if _ALT_BACKEND is not None and _ALT_BACKEND_NAME == name:
            return _ALT_BACKEND
        from .backends import get_backend
        backend = get_backend(name)
        if not backend.load():
            err = backend.get_error() or f"failed to load {name} backend"
            raise RuntimeError(err)
        _ALT_BACKEND = backend
        _ALT_BACKEND_NAME = name
        return backend


def _run_post_pipeline(
    task: TranscriptionTask,
    segments_data: list[dict[str, Any]],
    detected_lang: str,
    log_cb: Callable[[str], None] | None,
) -> int:
    """Diarisation + alignment + speaker_count for the writer.

    Returns the number of distinct speakers detected (0 if
    diarisation is disabled / unavailable / failed). Mutates
    ``segments_data`` in place with speaker labels.
    """
    speaker_count = 0
    if config.get("diarization_enabled", False) and not task.cancelled:
        try:
            from . import diarization as _diar

            if _diar.is_available():
                log("Diarising speakers...", log_cb)
                num_speakers = int(config.get("diarization_num_speakers", -1))
                threshold = float(config.get("diarization_cluster_threshold", 0.5))
                diar_segments = _diar.diarize(
                    task.file_path,
                    num_speakers=num_speakers,
                    cluster_threshold=threshold,
                )
                _diar.assign_speakers_to_segments(segments_data, diar_segments)
                speakers = sorted({s.speaker for s in diar_segments})
                speaker_count = len(speakers)
                log(f"Diarisation: {len(speakers)} speaker(s) — {', '.join(speakers)}",
                    log_cb)
            else:
                log(f"Diarisation skipped: {_diar.availability_reason()}", log_cb)
        except Exception as e:  # noqa: BLE001
            log(f"Diarisation failed (continuing without speakers): {e}", log_cb)

    # Word-level alignment refinement via stable-ts (opt-in).
    if config.get("alignment", "none") == "stable_ts":
        try:
            from . import alignment as _align
            if _align.is_available():
                log("Refining word timestamps via stable-ts...", log_cb)
                ok = _align.refine_word_timestamps_in_place(
                    task.file_path,
                    segments_data,
                    language=detected_lang or None,
                )
                if ok:
                    log("Word alignment refined.", log_cb)
                else:
                    # Surfaced as a WARN-style line — alignment was
                    # requested but produced no refinement (most
                    # commonly a tokenizer / language mismatch). The
                    # user sees this in the console; previous code
                    # silently swallowed the skip.
                    log(
                        "WARN: Word alignment requested but stable-ts "
                        "returned no refined words. Keeping original "
                        "word timestamps.",
                        log_cb,
                    )
            else:
                log(
                    f"WARN: Alignment skipped — {_align.availability_reason()}. "
                    "Install stable-ts to enable.",
                    log_cb,
                )
        except Exception as e:  # noqa: BLE001
            log(f"WARN: Alignment failed (continuing without refinement): {e}", log_cb)

    # Hallucination detector (opt-in, default ON). Runs last so it
    # sees the final diarised/aligned text. Any flagged segments get
    # ``suspect=True`` + ``suspect_reason`` which the writers carry
    # through to JSON and the viewer renders in red.
    if config.get("hallucination_detect_enabled", True):
        try:
            from . import hallucination as _hall
            flagged = _hall.annotate_segments(segments_data)
            if flagged:
                log(
                    f"Hallucination detector flagged {flagged} segment(s) "
                    "as suspect — open the transcript viewer to review.",
                    log_cb,
                )
        except Exception as e:  # noqa: BLE001
            log(f"Hallucination detector failed (continuing): {e}", log_cb)

    # Auto-chapter detection (v0.8 Phase 3). Pure heuristic by
    # default; if the LLM is enabled + loaded, chapter titles are
    # LLM-generated. Chapters land in a sidecar JSON next to the
    # other writer outputs (``<base>.chapters.json``) so existing
    # writers (SRT / VTT / TXT / JSON) keep their shape and the
    # viewer / external tools can read chapters independently.
    task._chapters_for_writer = []  # type: ignore[attr-defined]
    if config.get("auto_chapters_enabled", True) and not task.cancelled:
        try:
            from . import chapters as _chap
            runner = _maybe_get_llm_runner()
            chapter_list = _chap.build_chapters(
                segments_data,
                runner=runner,
                min_chapter_seconds=float(config.get("chapter_min_seconds", 60.0)),
                gap_seconds=float(config.get("chapter_gap_seconds", 2.5)),
            )
            if chapter_list:
                task._chapters_for_writer = chapter_list  # type: ignore[attr-defined]
                log(
                    f"Detected {len(chapter_list)} chapter(s) in the transcript.",
                    log_cb,
                )
        except Exception as e:  # noqa: BLE001
            log(f"Auto-chapter detection failed (continuing): {e}", log_cb)

    return speaker_count


def _maybe_get_llm_runner() -> Any | None:
    """Return a loaded LLMRunner when the AI Layer is on, else None.

    Wraps every failure mode (dep missing, model file missing, load
    error) so a broken LLM never blocks transcription.
    """
    if not config.get("ai_enabled", False):
        return None
    try:
        from . import llm as _llm
        if not _llm.runtime_available():
            return None
        model_path = (config.get("ai_model_path") or "").strip()
        if not model_path:
            model_path = str(_llm.default_model_path())
        if not _llm.is_model_present(Path(model_path)):
            return None
        runner = _llm.LLMRunner(_llm.LLMConfig(model_path=model_path))
        runner.load()
        return runner
    except Exception:  # noqa: BLE001
        return None


def _write_chapter_sidecar(base: str, chapters: list[dict[str, Any]]) -> str | None:
    """Write ``<base>.chapters.json`` atomically. Returns the path or None."""
    if not chapters:
        return None
    import json as _json
    path = base + ".chapters.json"
    part = f"{path}.{os.getpid()}-{threading.get_ident()}.part"
    try:
        with open(part, "w", encoding="utf-8", newline="\n") as f:
            _json.dump(chapters, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(part, path)
    except Exception:
        try:
            os.unlink(part)
        except OSError:
            pass
        return None
    return path


def transcribe(
    task: TranscriptionTask,
    progress_cb: Callable[[int], None] | None = None,
    log_cb: Callable[[str], None] | None = None,
    language_cb: Callable[[str, float], None] | None = None,
) -> None:
    # Backend dispatch — when the user has chosen a non-default
    # engine via config["transcribe_backend"], delegate to a backend
    # implementation. The original faster_whisper code below remains
    # the default path so the existing unit + smoke tests keep
    # working without monkeypatch churn.
    runtime_cfg = load_config()
    # Per-folder overrides: a .whisperproject.json next to (or above)
    # the source file is applied to the module-level config for the
    # duration of this task. We layer the overrides on top of
    # `config` (not the freshly-loaded runtime_cfg) so a test or
    # caller that has monkeypatched `config` still wins where the
    # override doesn't speak.
    try:
        from .config import load_project_overrides
        project_overrides = load_project_overrides(task.file_path)
        for k, v in project_overrides.items():
            if isinstance(v, dict) and isinstance(config.get(k), dict):
                _deep_merge_dict(config[k], v)
            else:
                config[k] = v
    except Exception:  # noqa: BLE001
        pass

    # Refresh runtime-mutable keys from runtime_cfg ONLY when the
    # in-memory ``config`` doesn't already carry a value for them
    # (e.g. a test has monkeypatched ``transcriber.config`` and we
    # must respect that). Runs BEFORE backend dispatch so both
    # faster_whisper and whisper_cpp paths see the same diarization
    # / alignment knobs and per-folder overrides win for the keys
    # they actually speak.
    for key, default in (
        ("diarization_enabled", False),
        ("diarization_num_speakers", -1),
        ("diarization_cluster_threshold", 0.5),
        ("alignment", "none"),
    ):
        if key not in config:
            config[key] = runtime_cfg.get(key, default)
    config["diarization_enabled"] = bool(config["diarization_enabled"])
    config["diarization_num_speakers"] = int(config["diarization_num_speakers"])
    config["diarization_cluster_threshold"] = float(
        config["diarization_cluster_threshold"]
    )
    config["alignment"] = str(config["alignment"])

    backend_name = (
        str(config.get("transcribe_backend")
            or runtime_cfg.get("transcribe_backend")
            or "faster_whisper").strip().lower()
    )
    if backend_name and backend_name != "faster_whisper":
        _transcribe_via_alt_backend(
            backend_name, task, progress_cb, log_cb, language_cb
        )
        return

    global MODEL
    while not MODEL_READY:
        if MODEL_ERROR:
            raise RuntimeError(MODEL_ERROR)
        time.sleep(0.5)

    # Optional Demucs vocal-separation pre-process (v0.8 Phase 2).
    # Returns the input path unchanged when demucs isn't installed or
    # the feature is off, so this is safe to always call.
    audio_path = task.file_path
    if config.get("demucs_enabled", False):
        try:
            from . import separator as _sep
            audio_path = _sep.separate_vocals(
                task.file_path,
                enabled=True,
                log=log_cb,
            )
        except Exception as e:  # noqa: BLE001
            log(f"Demucs separation failed (using original audio): {e}", log_cb)
            audio_path = task.file_path

    duration = get_duration(audio_path)
    start = time.time()
    log(f"Processing: {audio_path}", log_cb)

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

    segments, info = runner.transcribe(audio_path, **transcribe_kwargs)

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

    # Speaker diarization (opt-in) + word-level alignment (opt-in).
    detected_lang = str(getattr(info, "language", "") or "")
    speaker_count = _run_post_pipeline(task, segments_data, detected_lang, log_cb)

    written = _write_outputs(
        base,
        segments_data,
        task.file_path,
        lang=detected_lang,
        speaker_count=speaker_count,
    )
    chapters_attr = getattr(task, "_chapters_for_writer", None) or []
    chapter_path = _write_chapter_sidecar(base, chapters_attr)
    if chapter_path:
        written.append(chapter_path)
    log(f"Wrote {len(written)} output file(s): {', '.join(os.path.basename(p) for p in written)}",
        log_cb)

    if progress_cb:
        progress_cb(100)

    elapsed = time.time() - start
    log(f"Done in {elapsed:.2f}s", log_cb)


def _transcribe_via_alt_backend(
    backend_name: str,
    task: TranscriptionTask,
    progress_cb: Callable[[int], None] | None,
    log_cb: Callable[[str], None] | None,
    language_cb: Callable[[str, float], None] | None,
) -> None:
    """Drive a non-default backend through the same writers + diarisation."""
    backend = _get_alt_backend(backend_name)
    duration = get_duration(task.file_path)
    start = time.time()
    log(f"Processing ({backend_name}): {task.file_path}", log_cb)

    want_words = bool(config.get("word_timestamps", False))
    vad_params = _vad_parameters()

    segments_data, lang_info = backend.transcribe_to_segments(
        task.file_path,
        language=getattr(task, "language", None) or None,
        want_words=want_words,
        vad_parameters=vad_params,
        initial_prompt=config.get("initial_prompt") or None,
        hotwords=config.get("hotwords") or None,
        batch_size=int(config.get("batch_size", 16)),
        progress_cb=progress_cb,
        log_cb=log_cb,
        cancelled=lambda: bool(task.cancelled),
        paused=lambda: bool(task.paused),
        duration=duration,
    )

    if lang_info.language:
        if language_cb:
            try:
                language_cb(lang_info.language, lang_info.probability)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(task, "detected_language"):
            task.detected_language = lang_info.language
            task.language_probability = lang_info.probability

    if task.cancelled:
        log("Task cancelled", log_cb)
        return

    base = os.path.splitext(task.file_path)[0]
    # Defensive str cast: backends may emit None for language when
    # they couldn't detect. The faster_whisper path already
    # normalises via str(getattr(info, "language", "") or "")
    # at the call site — mirror that defensive style here so
    # downstream consumers (writer template, post-pipeline) never
    # see "None" as a stringified language code.
    detected_lang = str(lang_info.language or "")
    speaker_count = _run_post_pipeline(task, segments_data, detected_lang, log_cb)
    written = _write_outputs(
        base,
        segments_data,
        task.file_path,
        lang=detected_lang,
        speaker_count=speaker_count,
    )
    chapters_attr = getattr(task, "_chapters_for_writer", None) or []
    chapter_path = _write_chapter_sidecar(base, chapters_attr)
    if chapter_path:
        written.append(chapter_path)
    log(
        f"Wrote {len(written)} output file(s): "
        f"{', '.join(os.path.basename(p) for p in written)}",
        log_cb,
    )
    if progress_cb:
        progress_cb(100)
    elapsed = time.time() - start
    log(f"Done in {elapsed:.2f}s", log_cb)
