"""Map raw exceptions → ``(user_message, suggestion)`` pairs.

Whisper's failure modes can be opaque to a non-technical user
("CUDA out of memory", "FileNotFoundError: silero_vad_v6.onnx",
"OSError: [WinError 5] Access is denied"). This table catches the
common cases and turns them into one-sentence prose + one-sentence
fix.

The catch-all at the bottom returns the exception text verbatim so
nothing is silently swallowed — the dialog still shows what went
wrong, just without a fix hint.
"""
from __future__ import annotations

import os
import re
from typing import Iterable


# Each entry: regex pattern (matched against ``type(exc).__name__ :
# str(exc)``) → (friendly, suggestion). Patterns are checked in order
# so put the most specific ones first.
_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"FileNotFoundError.*ffmpeg|FileNotFoundError.*ffprobe", re.I),
        "ffmpeg or ffprobe is missing.",
        "Reinstall the app — the bundled binaries should sit next to the exe in a `bin/` folder.",
    ),
    (
        re.compile(r"FileNotFoundError.*silero", re.I),
        "The Whisper VAD model file is missing from the bundle.",
        "Reinstall the app — the bundled faster-whisper assets did not extract correctly.",
    ),
    (
        re.compile(r"FileNotFoundError.*model\.bin|FileNotFoundError.*model_path", re.I),
        "The Whisper model files are not on disk.",
        "Click Transcribe again to trigger the download dialog, or pick a different Model Hub Folder from the Help menu.",
    ),
    (
        re.compile(r"(CUDA out of memory|cuBLAS).*", re.I),
        "Your GPU ran out of memory.",
        "Close other GPU-heavy apps (browser tabs with video, games) and try again. Or set device=cpu in config.json.",
    ),
    (
        re.compile(r"cublas64.*not found|cudnn_ops.*not found|cudnn.*missing", re.I),
        "CUDA libraries are missing or the wrong version.",
        "Install the matching CUDA + cuDNN runtime, OR set device=cpu in config.json to run on CPU.",
    ),
    (
        re.compile(r"PermissionError.*\.srt|PermissionError.*\.json|PermissionError.*\.txt", re.I),
        "Could not write the subtitle file — it is open in another program.",
        "Close any media player or text editor showing the output file and try again.",
    ),
    (
        re.compile(r"PermissionError.*", re.I),
        "Access denied while writing to disk.",
        "Make sure the source file's folder is writable, or pick a folder under your user profile.",
    ),
    (
        re.compile(r"requests\.exceptions\.ConnectionError|ConnectionError.*", re.I),
        "Could not reach the model download server.",
        "Check your internet connection and any VPN / firewall, then try again.",
    ),
    (
        re.compile(r"requests\.exceptions\.Timeout|TimeoutError", re.I),
        "The download server took too long to respond.",
        "Check your network and retry — large files resume from where they stopped.",
    ),
    (
        re.compile(r"ffprobe failed|ffprobe timed out|ffmpeg.*exited", re.I),
        "ffmpeg/ffprobe could not read the media file.",
        "Make sure the file is a real audio/video file and not corrupt. Try playing it in VLC first.",
    ),
    (
        re.compile(r"OSError.*No space left|disk full", re.I),
        "Your disk is full.",
        "Free at least 5 GB and try again.",
    ),
    (
        re.compile(r"ImportError.*faster.whisper|ModuleNotFoundError.*faster.whisper", re.I),
        "The faster-whisper Python package is missing.",
        "Run `pip install -r requirements.txt` (or reinstall the app).",
    ),
    (
        re.compile(r"ImportError.*tkinterdnd2|ModuleNotFoundError.*tkinterdnd2", re.I),
        "Drag-and-drop support is missing (tkinterdnd2 not installed).",
        "Run `pip install tkinterdnd2` — you can still use the Browse button without it.",
    ),
]


def friendly_error(
    exc: BaseException,
    *,
    file_path: str | None = None,
) -> tuple[str, str]:
    """Return ``(message, suggestion)`` for an exception.

    Falls back to ``(str(exc), "")`` when no rule matches — the user
    still sees the raw error so a bug-reporter can describe it.
    """
    needle = f"{type(exc).__name__}: {exc}"
    for pat, msg, hint in _RULES:
        if pat.search(needle):
            return msg, hint
    return _fallback(exc, file_path)


def _fallback(exc: BaseException, file_path: str | None) -> tuple[str, str]:
    text = str(exc).strip() or type(exc).__name__
    if file_path:
        base = os.path.basename(file_path)
        text = f"While processing {base}: {text}"
    return text, ""


def all_patterns() -> Iterable[str]:
    """For tests — return the regex source strings."""
    return [pat.pattern for pat, _, _ in _RULES]
