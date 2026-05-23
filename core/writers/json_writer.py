"""JSON writer: list of segment dicts, indented for readability."""
from __future__ import annotations

import json
import math


def _safe_float(value: object, default: float = 0.0) -> float:
    """Coerce to a finite float — NaN/Inf become ``default``.

    Strict JSON parsers reject NaN/Infinity; a buggy backend that
    produced non-finite timestamps would silently corrupt every
    downstream consumer if we serialised them as-is.
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
        out.append({
            "start": _safe_float(seg.get("start", 0.0)),
            "end": _safe_float(seg.get("end", 0.0)),
            "text": (seg.get("text") or "").strip(),
        })
    # allow_nan=False — every consumer expects strict JSON.
    return json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
