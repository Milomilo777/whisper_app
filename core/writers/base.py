"""Shared helpers for the writers package."""
from __future__ import annotations


def fmt_srt_time(seconds: float) -> str:
    """SRT-style ``HH:MM:SS,ms`` (comma decimal mark)."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{sec:02d},{ms:03d}"


def fmt_vtt_time(seconds: float) -> str:
    """WebVTT ``HH:MM:SS.ms`` (period decimal mark)."""
    return fmt_srt_time(seconds).replace(",", ".")


def fmt_lrc_time(seconds: float) -> str:
    """LRC ``[mm:ss.xx]`` lyric timestamp."""
    if seconds < 0:
        seconds = 0.0
    minutes, rem = divmod(seconds, 60)
    return f"[{int(minutes):02d}:{rem:05.2f}]"


def normalize_text(text: str) -> str:
    """Trim and collapse internal whitespace runs to a single space."""
    return " ".join((text or "").split())
