"""Video Tiling: play one live stream as an N×N grid via ffplay.

yt-dlp streams the source to stdout; ffplay reads that and applies the
``tile`` video filter to fill the screen with an N×N grid of the source —
a "video wall" for a single channel (the use case from the maintainer's
github.com/translation-robot/video-tiler). One yt-dlp + one ffplay
process piped together; cross-platform, no window-manager tricks.

ffplay is NOT bundled with the app (only ffmpeg/ffprobe are), so it is
resolved via :func:`core.paths.bundled_binary` and the UI degrades to a
clear "add ffplay" message when it's missing — keeping the base download
small while the feature is available to anyone who drops ffplay in ``bin/``
or has it on PATH.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from typing import Callable, Optional

from .paths import bundled_binary

# Some hosts serve better formats to a desktop browser UA.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
)

MIN_DIVISIONS = 1
MAX_DIVISIONS = 8


def ffplay_path() -> str:
    """Bundled bin/ffplay[.exe] if present, else the bare name (PATH)."""
    return bundled_binary("ffplay")


def ffplay_available() -> bool:
    """True if an ffplay binary can be found (bundled or on PATH)."""
    p = ffplay_path()
    return os.path.isfile(p) or shutil.which(p) is not None


def _clamp_divisions(divisions: int) -> int:
    try:
        n = int(divisions)
    except (TypeError, ValueError):
        n = 3
    return max(MIN_DIVISIONS, min(MAX_DIVISIONS, n))


def build_tile_filter(divisions: int) -> str:
    """ffmpeg -vf chain that tiles the source into an n×n grid.

    Grabs n*n successive frames and arranges them in a grid, bumping fps so
    the grid refreshes at the source rate (matches the reference tool).
    """
    n = _clamp_divisions(divisions)
    return f"fps=source_fps*{n}*{n},tile={n}x{n}"


def build_commands(
    yt_dlp: str,
    ffplay: str,
    url: str,
    divisions: int,
    fmt: Optional[str] = None,
) -> tuple[list[str], list[str]]:
    """Return ``(yt_dlp_argv, ffplay_argv)`` for the piped pipeline.

    ``--`` guards the URL so a "-"-prefixed value can't be parsed as a
    yt-dlp option (same hardening as the download path).
    """
    yt_cmd = [
        yt_dlp, "--user-agent", _USER_AGENT, "-4",
        "-f", fmt or "bestvideo+bestaudio/best",
        "-o", "-", "--quiet", "--no-warnings", "--", url,
    ]
    ffplay_cmd = [
        ffplay, "-autoexit", "-loglevel", "error", "-hide_banner", "-fs",
        "-vf", build_tile_filter(divisions), "-i", "-",
    ]
    return yt_cmd, ffplay_cmd


class TilingController:
    """Start/stop a single yt-dlp→ffplay tiling pipeline."""

    def __init__(self) -> None:
        self._yt: Optional[subprocess.Popen] = None
        self._ffplay: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            return self._ffplay is not None and self._ffplay.poll() is None

    def start(
        self,
        url: str,
        divisions: int,
        fmt: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Launch the pipeline. Raises FileNotFoundError if ffplay is absent
        or RuntimeError on a blank URL; the caller surfaces the message."""
        url = (url or "").strip()
        if not url:
            raise RuntimeError("Enter a stream URL first.")
        if not ffplay_available():
            raise FileNotFoundError(
                "Video Tiling needs ffplay, which isn't bundled. Put "
                "ffplay[.exe] in the app's bin folder (it ships with the "
                "full ffmpeg build) or install ffmpeg so ffplay is on PATH."
            )
        self.stop()
        yt_cmd, ffplay_cmd = build_commands(
            bundled_binary("yt-dlp"), ffplay_path(), url, divisions, fmt
        )
        if log:
            log(f"Tiling {url} into a {_clamp_divisions(divisions)}×"
                f"{_clamp_divisions(divisions)} grid…")
        # Hide yt-dlp's console flash on Windows; ffplay keeps its own
        # SDL video window (CREATE_NO_WINDOW only suppresses the console).
        yt_kwargs: dict = {}
        if os.name == "nt":
            yt_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        with self._lock:
            self._yt = subprocess.Popen(
                yt_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                **yt_kwargs,
            )
            self._ffplay = subprocess.Popen(
                ffplay_cmd, stdin=self._yt.stdout, stderr=subprocess.DEVNULL,
            )
            # Let ffplay own the read end so yt-dlp gets SIGPIPE if ffplay dies.
            if self._yt.stdout:
                self._yt.stdout.close()

    def stop(self) -> None:
        with self._lock:
            for proc in (self._ffplay, self._yt):
                try:
                    if proc is not None and proc.poll() is None:
                        proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
            self._ffplay = None
            self._yt = None
