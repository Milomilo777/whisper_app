"""Tab-separated values writer (used by Audacity Labels and many editors)."""
from __future__ import annotations

from .base import normalize_text


def write(segments: list[dict], audio_path: str = "") -> str:
    rows: list[str] = ["start\tend\ttext"]
    for seg in segments:
        text = normalize_text(seg.get("text", "")).replace("\t", " ")
        start_ms = int(round(float(seg["start"]) * 1000))
        end_ms = int(round(float(seg["end"]) * 1000))
        rows.append(f"{start_ms}\t{end_ms}\t{text}")
    return "\n".join(rows) + "\n"
