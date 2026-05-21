"""Vocal separation pre-process — Demucs htdemucs (v0.8 Phase 2).

Some audio (noisy podcasts, songs with thick instrumentation,
phone-quality field recordings) hallucinates Whisper. Running
Demucs over the file first and feeding Whisper just the vocals
stem drops WER significantly on those inputs. Reference:
dev.to/codesugar 2026 benchmark.

Integration shape:

  * :func:`separate_vocals` takes an input audio path, runs Demucs
    if installed + enabled in config, and returns a path to the
    separated vocals WAV. If Demucs isn't installed OR the toggle
    is off, returns the input path unchanged — callers don't need
    a special "Demucs missing" code path.
  * Outputs go to ``user_cache_dir() / "demucs"`` so repeat
    transcriptions of the same source don't re-run separation.
  * Cache hit by file mtime + size + chosen model; cleared by the
    "Clear demucs cache" button in Advanced (future work).

Demucs is a heavy dependency (~150 MB model + torch ≥ 2.0). The
function is a no-op when the package isn't installed; tests
verify that fall-through.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .config import user_cache_dir

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "htdemucs"


class SeparatorUnavailable(RuntimeError):
    """Raised when the demucs package isn't installed."""


def is_available() -> bool:
    try:
        import demucs  # type: ignore[import-not-found] # noqa: F401
    except ImportError:
        return False
    return True


def availability_reason() -> str:
    if is_available():
        return ""
    return (
        "demucs not installed — `pip install demucs` to enable "
        "vocal-separation pre-processing."
    )


# ---------------------------------------------------------------- cache key


def _cache_key(audio_path: str, model: str) -> str:
    """Stable cache key from file size + mtime + model name.

    Hashing the file content would be correct-but-slow on multi-GB
    inputs. Size + mtime catches the common edit-then-re-transcribe
    case without paying the hash cost.
    """
    try:
        st = os.stat(audio_path)
        token = f"{audio_path}|{st.st_size}|{int(st.st_mtime)}|{model}"
    except OSError:
        token = f"{audio_path}|missing|{model}"
    return hashlib.sha1(token.encode("utf-8")).hexdigest()[:16]


def cache_dir() -> Path:
    return user_cache_dir() / "demucs"


def _cached_vocals_path(audio_path: str, model: str) -> Path:
    return cache_dir() / f"{_cache_key(audio_path, model)}_vocals.wav"


# ---------------------------------------------------------------- entry point


def separate_vocals(
    audio_path: str,
    *,
    model: str = DEFAULT_MODEL,
    enabled: bool = True,
    log: Callable[[str], None] | None = None,
) -> str:
    """Return path to a vocals-only WAV for the input.

    Behaviour matrix:
      * ``enabled=False``                       → return ``audio_path``
      * ``demucs`` not installed                → return ``audio_path``
        + log a one-line "skipped: demucs missing" warning
      * cache hit                               → return cached path
      * cache miss → run demucs → return new   → return separated path

    Never raises on demucs-runtime issues; falls back to the
    untouched input so the user still gets a transcript.
    """
    if not enabled:
        return audio_path
    if not is_available():
        if log:
            log(f"Demucs skipped: {availability_reason()}")
        return audio_path

    cached = _cached_vocals_path(audio_path, model)
    if cached.exists() and cached.stat().st_size > 1024:
        if log:
            log(f"Demucs cache hit → {cached}")
        return str(cached)

    cache_dir().mkdir(parents=True, exist_ok=True)
    out_dir = Path(tempfile.mkdtemp(prefix="demucs_", dir=str(cache_dir())))

    try:
        _run_demucs_cli(audio_path, out_dir, model=model, log=log)
    except Exception as e:  # noqa: BLE001
        logger.warning("Demucs run failed: %s — using original audio", e)
        if log:
            log(f"Demucs failed ({e}); falling back to original audio.")
        return audio_path

    # Demucs writes to ``{out_dir}/{model}/{stem_name}/vocals.wav`` —
    # locate it. Some Demucs versions vary the layout; recursively
    # search for a vocals.wav inside out_dir as a robust fallback.
    found = _find_vocals_in(out_dir)
    if found is None:
        if log:
            log("Demucs produced no vocals.wav; using original audio.")
        return audio_path

    try:
        os.replace(str(found), str(cached))
    except OSError:
        # Cross-drive replace can fail; fall back to copy+remove.
        try:
            import shutil
            shutil.copyfile(str(found), str(cached))
        except OSError as e:
            if log:
                log(f"Could not cache vocals stem: {e}")
            return str(found)
    if log:
        log(f"Demucs vocals → {cached}")
    return str(cached)


def _find_vocals_in(directory: Path) -> Path | None:
    for p in directory.rglob("vocals.wav"):
        return p
    return None


def _run_demucs_cli(
    audio_path: str,
    out_dir: Path,
    *,
    model: str,
    log: Callable[[str], None] | None = None,
) -> None:
    """Invoke demucs via its CLI entry point.

    The Python API also works but the CLI is simpler to call and
    is stable across demucs releases.
    """
    cmd = [
        "python", "-m", "demucs",
        "--two-stems", "vocals",
        "-n", model,
        "-o", str(out_dir),
        audio_path,
    ]
    if log:
        log(f"Running demucs: {' '.join(cmd)}")
    kwargs: dict[str, object] = {
        "check": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": 600,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.run(cmd, **kwargs)  # type: ignore[arg-type]
