"""JSON writer: list of segment dicts, indented for readability.

Preserves ``words`` (with their probabilities) when present so downstream
karaoke tools can re-render without re-running Whisper. Also preserves
``speaker`` when the diarisation pipeline tagged the segment.
"""
from __future__ import annotations

import json


import math


def _safe_float(value: object, default: float = 0.0) -> float:
    """Coerce to a finite float — NaN/Inf become ``default``.

    Strict JSON parsers (browsers, Go encoding/json, Rust serde)
    reject ``NaN`` / ``Infinity``. A buggy backend that produces
    non-finite timestamps would silently corrupt every downstream
    consumer of our JSON output if we serialised them as-is.
    """
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return f


def write(segments: list[dict], audio_path: str = "") -> str:
    out: list[dict] = []
    for seg in segments:
        item: dict = {
            "start": _safe_float(seg.get("start", 0.0)),
            "end": _safe_float(seg.get("end", 0.0)),
            "text": (seg.get("text") or "").strip(),
        }
        speaker = seg.get("speaker")
        if speaker not in (None, ""):
            item["speaker"] = str(speaker)
        words = seg.get("words")
        if words:
            item["words"] = [
                {
                    "start": _safe_float(w.get("start", item["start"]),
                                         item["start"]),
                    "end": _safe_float(w.get("end", item["end"]),
                                       item["end"]),
                    "word": w.get("word", ""),
                    "probability": _safe_float(w.get("probability", 0.0)),
                }
                for w in words
            ]
        out.append(item)
    # allow_nan=False — every consumer of this JSON expects strict
    # output; we've already _safe_float-ed every numeric field above
    # so this can no longer raise in practice but guards against
    # future regressions.
    return json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
