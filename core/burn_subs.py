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
import shutil
import subprocess
import tempfile
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
    # ffmpeg's `subtitles=` value is parsed as a libavfilter *filter graph*,
    # where ' , ; [ ] are metacharacters. The SRT path is derived from the
    # media filename, and for a downloaded video that name comes straight
    # from the (attacker-influenced) yt-dlp title — which keeps ' [ ] , by
    # default. Interpolating such a name into the graph string both breaks
    # burning for legitimately-punctuated titles AND is a filter-injection
    # vector. Rather than juggle ffmpeg's brittle multi-level escaping, copy
    # the SRT to a temp file with a graph-safe ASCII basename and burn from
    # there. The only remaining special char is the Windows drive-letter
    # colon (the temp DIRECTORY can't contain ' , ; [ ] — those are illegal
    # in Windows usernames, and POSIX temp dirs don't use them); escape it
    # the same proven way, but only on Windows so a legal POSIX colon in the
    # temp path isn't mangled.
    tmp_dir = tempfile.mkdtemp(prefix="burnsubs_")
    safe_srt_file = os.path.join(tmp_dir, "subs.srt")
    try:
        shutil.copyfile(srt_path, safe_srt_file)
        filter_path = safe_srt_file.replace("\\", "/")
        if os.name == "nt":
            filter_path = filter_path.replace(":", "\\\\:")
        cmd = [
            ffmpeg,
            "-y",
            "-i", video_path,
            "-vf", f"subtitles={filter_path}",
            "-c:a", "copy",
        ]
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(out_path)

        kwargs: dict[str, Any] = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            subprocess.run(cmd, check=True, timeout=timeout, **kwargs)
        except subprocess.CalledProcessError as e:
            msg = (e.stderr or b"").decode("utf-8", "replace")[-1000:]
            raise RuntimeError(f"ffmpeg failed to burn subtitles: {msg}") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"ffmpeg timed out burning subtitles after {timeout}s"
            ) from e
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
