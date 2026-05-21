"""Auto-chapter markers from a finished transcript (v0.8 Phase 3).

The simplest robust heuristic: cut a new chapter whenever there is
a **long inter-segment silence** AND the cumulative chapter
duration crossed a minimum threshold. Modelled after PODTILE-lite
(arXiv 2410.16148) without the heavy LLM dep.

Two-step pipeline:

  1. :func:`detect_chapter_boundaries` walks the segment list and
     returns a list of `(start_seconds, end_seconds, segment_index_range)`.
     Pure Python, no model dependencies. Always available.
  2. (Optional) :func:`title_chapters_with_llm` runs each chapter
     through the local LLM (when installed) to label it with a
     6-word headline. Falls back to "Chapter N" when LLM isn't
     ready.

Output shape (what :func:`build_chapters` returns):

    [
      {"index": 0, "title": "Intro & guest welcome",
       "start": 0.0, "end": 215.4, "segment_start": 0, "segment_end": 27},
      ...
    ]

The viewer (future work) can use the start times for navigation
and the writer can append them to JSON. The chapters list is
self-contained — it doesn't mutate the underlying segments.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_MIN_CHAPTER_SECONDS = 60.0
DEFAULT_GAP_SECONDS = 2.5
DEFAULT_SENTENCE_TERMINATORS = ("?", "!", ".")


@dataclass(frozen=True)
class ChapterBoundary:
    start: float
    end: float
    segment_start: int
    segment_end: int  # inclusive


def detect_chapter_boundaries(
    segments: list[dict[str, Any]],
    *,
    min_chapter_seconds: float = DEFAULT_MIN_CHAPTER_SECONDS,
    gap_seconds: float = DEFAULT_GAP_SECONDS,
) -> list[ChapterBoundary]:
    """Cut chapters at long silences once the running chapter is long enough.

    A boundary forms when:
      * gap between segment ``i`` end and segment ``i+1`` start
        exceeds ``gap_seconds``, AND
      * the cumulative duration of the in-progress chapter has
        passed ``min_chapter_seconds``.

    Always returns at least one chapter covering the whole input
    when ``segments`` is non-empty; empty input → empty list.
    """
    if not segments:
        return []
    boundaries: list[ChapterBoundary] = []
    chapter_start_idx = 0
    chapter_start = float(segments[0].get("start", 0.0))
    for i in range(len(segments) - 1):
        cur_end = float(segments[i].get("end", segments[i].get("start", 0.0)))
        next_start = float(segments[i + 1].get("start", cur_end))
        gap = next_start - cur_end
        duration = cur_end - chapter_start
        if gap >= gap_seconds and duration >= min_chapter_seconds:
            boundaries.append(ChapterBoundary(
                start=chapter_start,
                end=cur_end,
                segment_start=chapter_start_idx,
                segment_end=i,
            ))
            chapter_start_idx = i + 1
            chapter_start = next_start
    # Close the trailing chapter on the final segment.
    last = segments[-1]
    last_end = float(last.get("end", last.get("start", 0.0)))
    boundaries.append(ChapterBoundary(
        start=chapter_start,
        end=last_end,
        segment_start=chapter_start_idx,
        segment_end=len(segments) - 1,
    ))
    return boundaries


# ---------------------------------------------------------------- titles


_FIRST_SENTENCE_RE = re.compile(r"^[^.!?\n]+[.!?]?")


def heuristic_title(segments: list[dict[str, Any]], boundary: ChapterBoundary,
                     *, max_words: int = 6) -> str:
    """Pull the first sentence of the chapter as a fallback title."""
    if boundary.segment_start >= len(segments):
        return "Chapter"
    text_parts: list[str] = []
    for idx in range(boundary.segment_start, boundary.segment_end + 1):
        if idx >= len(segments):
            break
        t = (segments[idx].get("text") or "").strip()
        if t:
            text_parts.append(t)
            if len(" ".join(text_parts).split()) >= max_words * 2:
                break
    combined = " ".join(text_parts).strip()
    if not combined:
        return "Chapter"
    m = _FIRST_SENTENCE_RE.match(combined)
    first = (m.group(0).strip() if m else combined).rstrip(".!? ")
    words = first.split()
    if len(words) > max_words:
        first = " ".join(words[:max_words]) + "…"
    return first or "Chapter"


def title_chapters_with_llm(
    segments: list[dict[str, Any]],
    boundaries: list[ChapterBoundary],
    *,
    runner: "Any | None" = None,
) -> list[str]:
    """Use the local LLM to label each chapter; fall back to heuristic.

    ``runner`` is a :class:`core.llm.LLMRunner` (or any object with
    a compatible ``ask`` method). When ``None`` or unavailable, this
    returns the heuristic titles so the chapter list is always
    usable.
    """
    titles: list[str] = []
    for boundary in boundaries:
        if runner is None:
            titles.append(heuristic_title(segments, boundary))
            continue
        text = _slice_text(segments, boundary)
        try:
            raw = runner.ask(
                text,
                "Write a 4-7 word headline that summarises this "
                "chapter. Respond with only the headline, no quotes.",
            )
            raw = (raw or "").strip().strip('"').strip("'")
            if raw and len(raw) <= 120:
                titles.append(raw)
                continue
        except Exception as e:  # noqa: BLE001
            logger.debug("LLM titling failed: %s", e)
        titles.append(heuristic_title(segments, boundary))
    return titles


def _slice_text(segments: list[dict[str, Any]], boundary: ChapterBoundary) -> str:
    parts: list[str] = []
    for idx in range(boundary.segment_start, boundary.segment_end + 1):
        if idx >= len(segments):
            break
        t = (segments[idx].get("text") or "").strip()
        if t:
            parts.append(t)
    return " ".join(parts)


# ---------------------------------------------------------------- entry point


def build_chapters(
    segments: list[dict[str, Any]],
    *,
    runner: "Any | None" = None,
    min_chapter_seconds: float = DEFAULT_MIN_CHAPTER_SECONDS,
    gap_seconds: float = DEFAULT_GAP_SECONDS,
) -> list[dict[str, Any]]:
    """High-level entry point: detect + title in one call.

    Returns a list of chapter dicts ready to write into the JSON
    output sidecar.
    """
    boundaries = detect_chapter_boundaries(
        segments,
        min_chapter_seconds=min_chapter_seconds,
        gap_seconds=gap_seconds,
    )
    titles = title_chapters_with_llm(segments, boundaries, runner=runner)
    out: list[dict[str, Any]] = []
    for i, (b, title) in enumerate(zip(boundaries, titles)):
        out.append({
            "index": i,
            "title": title,
            "start": b.start,
            "end": b.end,
            "segment_start": b.segment_start,
            "segment_end": b.segment_end,
        })
    return out
