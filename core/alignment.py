"""Word-level alignment refinement via stable-ts (opt-in).

``stable_whisper`` (PyPI: ``stable-ts``) does dynamic-time-warping
on the cross-attention weights to lock down word start/end times to
± 50 ms accuracy, much better than Whisper's native word timestamps
which can wobble by 100–300 ms on short words.

We invoke it as a post-processor: after our segments are written, we
call ``stable_whisper.alignment.align`` against the same audio and the
segment text. The function returns refined segment + word lists, which
we splice back into the existing segments_data list so the JSON / SRT
writers pick up the new timestamps.

This module is intentionally tiny — no global state, no model
caching. stable-ts loads a separate (much smaller) Whisper model to
run the alignment; we keep it CPU-only by default to avoid GPU
contention with the main transcribe model.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """True iff stable-ts imports cleanly."""
    try:
        import stable_whisper  # type: ignore[import-not-found] # noqa: F401
    except ImportError:
        return False
    return True


def availability_reason() -> str:
    if is_available():
        return ""
    return "stable-ts Python package not installed"


def refine_word_timestamps_in_place(
    audio_path: str,
    segments_data: list[dict[str, Any]],
    *,
    language: str | None = None,
    model_name: str = "tiny",
) -> None:
    """Refine word timestamps in ``segments_data`` (in place).

    Each segment gets / replaces its ``words`` list with the DTW-
    refined timings. The segment ``start`` / ``end`` are not modified
    (we trust faster-whisper's segment-level timestamps); only the
    word grain inside each segment is updated.

    ``model_name`` controls which Whisper model stable-ts loads for
    the alignment pass — ``tiny`` is enough for word boundaries and
    keeps the memory footprint small (~75 MB).

    Raises ``RuntimeError`` if stable-ts is not installed.
    """
    if not is_available():
        raise RuntimeError(availability_reason())

    import stable_whisper  # type: ignore[import-not-found]

    if not segments_data:
        return

    # stable_whisper.align takes a list of {start, end, text} dicts
    # plus the audio path, and returns a WhisperResult with refined
    # word timings. Older versions exposed the function under
    # stable_whisper.alignment.align; newer ones at the top level.
    align = getattr(stable_whisper, "align", None)
    if align is None:
        align = getattr(stable_whisper, "alignment", None)
        if align is not None:
            align = getattr(align, "align", None)
    if align is None:
        raise RuntimeError("stable-ts: alignment function not found")

    model = stable_whisper.load_model(model_name)
    coarse = [
        {"start": float(s.get("start", 0.0)),
         "end": float(s.get("end", 0.0)),
         "text": str(s.get("text", ""))}
        for s in segments_data
    ]
    refined = align(model, audio_path, coarse, language=language or None)

    refined_segments = getattr(refined, "segments", None) or []
    if not refined_segments:
        return

    # Splice the refined word lists into segments_data, matching by
    # index (stable-ts preserves order when aligning a sequence).
    n = min(len(refined_segments), len(segments_data))
    for i in range(n):
        words = getattr(refined_segments[i], "words", None) or []
        seg_words: list[dict[str, Any]] = []
        for w in words:
            seg_words.append({
                "start": float(getattr(w, "start", 0.0)),
                "end": float(getattr(w, "end", 0.0)),
                "word": str(getattr(w, "word", "") or "").strip(),
                "probability": float(getattr(w, "probability", 1.0)),
            })
        segments_data[i]["words"] = seg_words
