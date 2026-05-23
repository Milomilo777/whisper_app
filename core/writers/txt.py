"""Plain-text transcript: one segment per line, no timestamps."""
from __future__ import annotations


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def write(segments: list[dict], audio_path: str = "") -> str:
    lines = [_normalize(seg.get("text", "")) for seg in segments]
    return "\n".join(lines) + "\n"
