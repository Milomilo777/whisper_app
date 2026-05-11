"""SubRip ``.srt`` writer."""
from __future__ import annotations

from .base import fmt_srt_time, normalize_text


def write(segments: list[dict], audio_path: str = "") -> str:
    out: list[str] = []
    for i, seg in enumerate(segments, 1):
        text = normalize_text(seg.get("text", ""))
        out.append(f"{i}")
        out.append(f"{fmt_srt_time(float(seg['start']))} --> {fmt_srt_time(float(seg['end']))}")
        out.append(text)
        out.append("")
    return "\n".join(out)
