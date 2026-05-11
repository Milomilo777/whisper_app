"""WebVTT ``.vtt`` writer.

If a segment has a ``words`` list, emit a karaoke-style cue with each word
wrapped in ``<HH:MM:SS.ms><c>word</c>`` markers — the convention recognised
by browsers when shown via ``<track>``.
"""
from __future__ import annotations

from .base import fmt_vtt_time, normalize_text


def _karaoke_payload(seg: dict) -> str:
    words = seg.get("words") or []
    if not words:
        return normalize_text(seg.get("text", ""))
    parts: list[str] = []
    for w in words:
        ts = fmt_vtt_time(float(w.get("start", seg["start"])))
        token = (w.get("word") or "").strip()
        if not token:
            continue
        if parts:
            parts.append(" ")
        parts.append(f"<{ts}><c>{token}</c>")
    return "".join(parts).strip()


def write(segments: list[dict], audio_path: str = "") -> str:
    out: list[str] = ["WEBVTT", ""]
    for seg in segments:
        out.append(f"{fmt_vtt_time(float(seg['start']))} --> {fmt_vtt_time(float(seg['end']))}")
        out.append(_karaoke_payload(seg))
        out.append("")
    return "\n".join(out)
