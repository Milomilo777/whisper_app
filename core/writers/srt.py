"""SubRip ``.srt`` writer."""
from __future__ import annotations

import math


def _fmt_srt_time(seconds: float) -> str:
    """SRT-style ``HH:MM:SS,ms`` (comma decimal mark)."""
    if seconds is None or not isinstance(seconds, (int, float)):
        seconds = 0.0
    # NaN / Inf are valid floats but produce garbage timestamps;
    # clamp to 0 so a buggy backend doesn't poison parsers.
    if not math.isfinite(float(seconds)) or seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{sec:02d},{ms:03d}"


def _normalize_text(text: str) -> str:
    """Trim + collapse internal whitespace to single spaces."""
    return " ".join((text or "").split())


def _escape_cue_separator(text: str) -> str:
    """Replace literal ``-->`` in cue text with a unicode arrow.

    SRT uses ``-->`` as the timecode separator on its own line;
    embedded occurrences in payload confuse some parsers.
    """
    if not text:
        return ""
    return text.replace("-->", "→")


def write(segments: list[dict], audio_path: str = "") -> str:
    out: list[str] = []
    for i, seg in enumerate(segments, 1):
        text = _escape_cue_separator(_normalize_text(seg.get("text", "")))
        out.append(f"{i}")
        out.append(
            f"{_fmt_srt_time(float(seg['start']))} --> "
            f"{_fmt_srt_time(float(seg['end']))}"
        )
        out.append(text)
        out.append("")
    return "\n".join(out)
