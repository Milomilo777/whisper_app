"""Timecode parsing + formatting helpers.

Pulled out into a tiny module of its own so both the yt-dlp download
service and any future feature (chapter slicing, future "transcribe
section" tweak) can import it without dragging in the rest of
download_service.

Accepted input shapes (whitespace-tolerant):

  * ``H:MM:SS[.ms]`` — e.g. ``"1:23:45"``, ``"0:00:51"``
  * ``MM:SS[.ms]``   — e.g. ``"5:30"``, ``"1:25.5"``
  * ``SS[.ms]``      — e.g. ``"90"``, ``"7.25"``

Any other shape (blank, garbled, negative, > 24 h) returns ``None``
so callers can treat "garbled" and "left blank" the same way.
"""
from __future__ import annotations

__all__ = ["parse_timecode", "fmt_timecode", "download_sections_arg"]

_MAX_TIMECODE_SECONDS = 86_400.0  # 24h sanity cap


def parse_timecode(raw: str | None) -> float | None:
    """Parse a user-typed timecode into seconds, or None on bad input."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    parts = s.split(":")
    if len(parts) > 3:
        return None
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if any(n < 0 for n in nums):
        return None
    # Reject sub-positions >= 60 in MM:SS / H:MM:SS shapes — that
    # would normally be a typo. SS-only is allowed to exceed 60
    # because the user might legitimately type "90" for 90 seconds.
    if len(nums) >= 2:
        if any(n >= 60 for n in nums[1:]):
            return None
    if len(parts) == 3:
        h, m, sec = nums
        total = h * 3600 + m * 60 + sec
    elif len(parts) == 2:
        m, sec = nums
        total = m * 60 + sec
    else:
        total = nums[0]
    if total < 0 or total > _MAX_TIMECODE_SECONDS:
        return None
    return total


def fmt_timecode(seconds: float) -> str:
    """Format seconds back into yt-dlp's preferred ``H:MM:SS[.SS]``."""
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    frac = seconds - total
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    base = f"{hours}:{minutes:02d}:{secs:02d}"
    # Preserve sub-second precision only when the caller supplied any —
    # avoids polluting argv with .00 for whole-second inputs.
    if frac > 0:
        suffix = f"{frac:.2f}".lstrip("0").rstrip("0").rstrip(".")
        if suffix:
            base = f"{base}{suffix}"
    return base


def download_sections_arg(
    start: float | None, end: float | None,
) -> str | None:
    """Build the ``--download-sections`` value, or ``None`` if both bounds unset.

    yt-dlp accepts ``*start-end``, ``*-end``, ``*start-`` — either
    bound may be left open.
    """
    if start is None and end is None:
        return None
    start_str = fmt_timecode(start) if start is not None else ""
    end_str = fmt_timecode(end) if end is not None else ""
    return f"*{start_str}-{end_str}"
