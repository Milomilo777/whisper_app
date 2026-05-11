"""JSON writer: list of segment dicts, indented for readability.

Preserves ``words`` (with their probabilities) when present so downstream
karaoke tools can re-render without re-running Whisper.
"""
from __future__ import annotations

import json


def write(segments: list[dict], audio_path: str = "") -> str:
    out: list[dict] = []
    for seg in segments:
        item: dict = {
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": (seg.get("text") or "").strip(),
        }
        words = seg.get("words")
        if words:
            item["words"] = [
                {
                    "start": float(w.get("start", item["start"])),
                    "end": float(w.get("end", item["end"])),
                    "word": w.get("word", ""),
                    "probability": float(w.get("probability", 0.0)),
                }
                for w in words
            ]
        out.append(item)
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"
