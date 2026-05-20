"""Markdown ``.md`` writer.

Layout:

  # <audio basename>

  **HH:MM:SS** Speaker name :  segment text...
  **HH:MM:SS** Speaker name :  next segment...

Speaker prefixes appear only when the segment carries a ``speaker``
field (set by the diarisation pipeline). Without speakers, the
heading is the audio basename and each segment is a single line:

  **HH:MM:SS**  segment text...

Stdlib only.
"""
from __future__ import annotations

import os

from .base import fmt_srt_time, normalize_text


def _fmt_md_time(seconds: float) -> str:
    """``HH:MM:SS`` — drops the millisecond fraction the SRT helper carries."""
    return fmt_srt_time(seconds).split(",")[0]


def write(segments: list[dict], audio_path: str = "") -> str:
    title = os.path.basename(audio_path) if audio_path else "Transcript"
    lines: list[str] = [f"# {title}", ""]
    for seg in segments:
        text = normalize_text(seg.get("text", ""))
        if not text:
            continue
        ts = _fmt_md_time(float(seg.get("start", 0.0)))
        speaker = (seg.get("speaker") or "").strip()
        if speaker:
            lines.append(f"**{ts}** _{speaker}:_ {text}")
        else:
            lines.append(f"**{ts}** {text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
