"""SubRip ``.srt`` writer.

If a segment carries a ``speaker`` field (set by the diarisation
pipeline), the SRT line is prefixed with ``Speaker N: ``. This is
the convention SubRip and most media players accept; downstream
viewers like VLC render it cleanly.
"""
from __future__ import annotations

from .base import fmt_srt_time, normalize_text


def write(segments: list[dict], audio_path: str = "") -> str:
    out: list[str] = []
    for i, seg in enumerate(segments, 1):
        text = normalize_text(seg.get("text", ""))
        speaker = (seg.get("speaker") or "").strip()
        if speaker:
            text = f"{speaker}: {text}"
        out.append(f"{i}")
        out.append(f"{fmt_srt_time(float(seg['start']))} --> {fmt_srt_time(float(seg['end']))}")
        out.append(text)
        out.append("")
    return "\n".join(out)
