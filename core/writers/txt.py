"""Plain-text transcript: one segment per line, no timestamps."""
from __future__ import annotations

from .base import normalize_text


def write(segments: list[dict], audio_path: str = "") -> str:
    lines = [normalize_text(seg.get("text", "")) for seg in segments]
    return "\n".join(lines) + "\n"
