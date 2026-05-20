"""Burn an SRT into a video via ffmpeg.

One pure function: ``burn(video_path, srt_path, out_path)``. Uses
ffmpeg's ``subtitles`` filter which renders the SRT as a vector
overlay on top of the video stream.

This is a one-shot synchronous call; on large videos it can take a
while. The caller (UI service) should run it in a background
thread and surface progress via the existing ``download_events``
or a similar queue.

Output is encoded as H.264 + AAC at copy-quality (no bitrate
re-target). Adjust by passing ``extra_args``.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any

from .paths import bundled_binary


def burn(
    video_path: str,
    srt_path: str,
    out_path: str,
    *,
    extra_args: list[str] | None = None,
    timeout: float = 3600.0,
) -> None:
    """Write ``out_path`` with the SRT subtitles burned into the video.

    Raises:
        FileNotFoundError if the video or srt is missing.
        RuntimeError      if ffmpeg returns non-zero.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"video not found: {video_path}")
    if not os.path.isfile(srt_path):
        raise FileNotFoundError(f"srt not found: {srt_path}")

    ffmpeg = bundled_binary("ffmpeg")
    # ffmpeg's `subtitles=` filter takes a file path that ffmpeg's
    # libavfilter resolves locally. On Windows the path must be
    # forward-slashed *and* the drive letter colon escaped.
    safe_srt = srt_path.replace("\\", "/").replace(":", "\\\\:")
    cmd = [
        ffmpeg,
        "-y",
        "-i", video_path,
        "-vf", f"subtitles={safe_srt}",
        "-c:a", "copy",
    ]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(out_path)

    kwargs: dict[str, Any] = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(cmd, check=True, timeout=timeout, **kwargs)
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or b"").decode("utf-8", "replace")[-1000:]
        raise RuntimeError(f"ffmpeg failed to burn subtitles: {msg}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"ffmpeg timed out burning subtitles after {timeout}s"
        ) from e
