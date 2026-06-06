"""Transcription-format CONVERSION via the faster-whisper JSON middle format.

Parse an existing transcript file into the universal segment list — a list of
``{start, end, text, ...}`` dicts, the same shape this app's JSON writer emits
and every ``core.writers`` text writer consumes — then re-emit it in any target
text format through the existing writers registry.

PARSE (input) formats, auto-detected by extension then content:

  * ``.json`` — this app's JSON output (a list of segment dicts).
  * ``.srt``  — SubRip.
  * ``.vtt``  — WebVTT.
  * ``.tsv``  — the ``start<TAB>end<TAB>text`` table this app's TSV writer emits
    (start/end in MILLISECONDS), tolerant of a header row.
  * ``.otr``  — oTranscribe (imported via
    :mod:`core.integrations.otranscribe`).

TXT is OUTPUT-ONLY: it carries no timestamps, so it cannot be parsed back into
segments (``parse_to_segments`` raises ``ConvertError`` for ``.txt``).

EMIT (output) formats: any text writer in ``core.writers.WRITERS``
(srt / vtt / tsv / txt / json / lrc / md). Binary writers (docx / pdf /
smtv_docx) are intentionally NOT offered here — they need extra context
(language / title) and are produced by the transcription pipeline.

Stdlib only; Tk-free. The two public seams are pure and testable:

    parse_to_segments(path) -> list[dict]
    convert_file(in_path, out_format, out_path=None) -> out_path
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from . import writers as _writers
from .integrations import otranscribe as _otr

__all__ = [
    "ConvertError",
    "PARSE_FORMATS",
    "OUTPUT_FORMATS",
    "parse_to_segments",
    "convert_file",
]


class ConvertError(ValueError):
    """Raised when an input cannot be parsed or a target format is unknown."""


# Formats we can PARSE into segments (input side). TXT is deliberately absent.
PARSE_FORMATS: tuple[str, ...] = ("json", "srt", "vtt", "tsv", "otr")

# Formats we can EMIT — the text writers in the registry (output side).
OUTPUT_FORMATS: tuple[str, ...] = tuple(sorted(_writers.WRITERS.keys()))


# --- timestamp parsing ------------------------------------------------------

# HH:MM:SS,mmm or HH:MM:SS.mmm (SRT uses comma, VTT uses period); the hour
# field is optional in WebVTT (MM:SS.mmm), so allow a 2- or 3-field clock.
_CUE = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*-->\s*"
    r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[,.](\d{1,3})"
)


def _clock_to_seconds(
    h: str | None, m: str, s: str, frac: str
) -> float:
    hours = int(h) if h else 0
    # Right-pad the fractional part to milliseconds (".5" -> 500ms).
    ms = int((frac + "000")[:3])
    return hours * 3600 + int(m) * 60 + int(s) + ms / 1000.0


# --- per-format parsers (return list of {start, end, text}) -----------------

def _parse_json(text: str, path: str) -> list[dict]:
    """Parse this app's JSON output — a list of segment dicts.

    Each entry must be an object; ``start``/``end`` coerce to float (missing
    end falls back to start), ``text`` is stripped. Per-word lists and
    ``speaker`` are carried through so a JSON->JSON / JSON->VTT round-trip
    keeps karaoke timing and speaker labels.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        raise ConvertError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, list):
        raise ConvertError(
            f"{path} JSON must be a list of segments, got {type(data).__name__}"
        )
    segments: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            start = float(entry.get("start", 0.0))
        except (TypeError, ValueError):
            start = 0.0
        try:
            end = float(entry.get("end", start))
        except (TypeError, ValueError):
            end = start
        body = (entry.get("text") or "").strip()
        if not body:
            continue
        seg: dict[str, Any] = {"start": start, "end": end, "text": body}
        speaker = entry.get("speaker")
        if speaker not in (None, ""):
            seg["speaker"] = str(speaker)
        words = entry.get("words")
        if isinstance(words, list):
            # Carry through only dict word entries. A non-dict element
            # (a bare string / number from hand-edited or externally
            # produced JSON) would make the downstream writers' w.get(...)
            # raise AttributeError and abort the whole conversion.
            valid_words = [w for w in words if isinstance(w, dict)]
            if valid_words:
                seg["words"] = valid_words
        segments.append(seg)
    return segments


def _parse_cue_format(text: str, path: str) -> list[dict]:
    """Parse SRT or WebVTT — both are cue blocks separated by blank lines.

    A cue is a block holding a ``-->`` timing line; everything after that line
    (within the block) is the cue body. The leading sequence number (SRT) and
    the ``WEBVTT`` header / ``NOTE`` / ``STYLE`` blocks (VTT) are skipped
    because they contain no timing line.
    """
    norm = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not norm:
        return []
    segments: list[dict] = []
    for block in re.split(r"\n\s*\n+", norm):
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        ts_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ts_idx is None:
            continue
        m = _CUE.search(lines[ts_idx])
        if not m:
            continue
        g = m.groups()
        start = _clock_to_seconds(g[0], g[1], g[2], g[3])
        end = _clock_to_seconds(g[4], g[5], g[6], g[7])
        # Strip WebVTT inline karaoke tags (<00:00:01.000><c>word</c>) down to
        # plain text so the body is the spoken words, not markup.
        body_lines = lines[ts_idx + 1:]
        body = " ".join(ln.strip() for ln in body_lines)
        body = re.sub(r"<[^>]+>", "", body).strip()
        if body:
            segments.append({"start": start, "end": end, "text": body})
    return segments


def _parse_tsv(text: str, path: str) -> list[dict]:
    """Parse the app's TSV (``start<TAB>end<TAB>text``; start/end in ms).

    A header row (non-numeric first field, e.g. the ``start`` literal this
    app's writer emits) is skipped. Rows with fewer than three tab fields or a
    non-numeric time are ignored rather than aborting the whole parse.
    """
    segments: list[dict] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not raw.strip():
            continue
        parts = raw.split("\t")
        if len(parts) < 3:
            continue
        start_raw, end_raw = parts[0].strip(), parts[1].strip()
        body = parts[2].strip()
        try:
            start = float(start_raw) / 1000.0
            end = float(end_raw) / 1000.0
        except (TypeError, ValueError):
            # Header row or malformed line — skip silently.
            continue
        if body:
            segments.append({"start": start, "end": end, "text": body})
    return segments


def _parse_otr(path: str) -> list[dict]:
    """Import an oTranscribe ``.otr`` by round-tripping through its SRT helper.

    ``core.integrations.otranscribe.otr_to_srt`` already infers end times from
    the next segment's start, so reusing it keeps a single source of truth for
    that contract.
    """
    srt_text = _otr.otr_to_srt(path)
    return _parse_cue_format(srt_text, path)


# --- public API -------------------------------------------------------------

def _detect_format(path: str, text: str | None) -> str:
    """Return one of ``PARSE_FORMATS`` for *path*, by extension then content.

    The extension is authoritative when recognised. ``.txt`` raises (output
    only). An unknown / missing extension falls back to content sniffing:
    a leading ``[``/``{`` => json, a ``WEBVTT`` header => vtt, a ``-->`` line
    => srt, a tab-delimited numeric table => tsv.
    """
    ext = Path(path).suffix.lower().lstrip(".")
    if ext == "txt":
        raise ConvertError(
            "TXT has no timestamps and cannot be converted FROM; it is an "
            "output-only format. Pick an .srt / .vtt / .tsv / .json / .otr "
            "source instead."
        )
    if ext in PARSE_FORMATS:
        return ext

    sniff = (text or "").lstrip()
    if not sniff:
        raise ConvertError(f"{path}: empty or unreadable input.")
    if sniff[0] in "[{":
        return "json"
    head = sniff[:64].upper()
    if head.startswith("WEBVTT"):
        return "vtt"
    if "-->" in sniff:
        return "srt"
    if "\t" in sniff.split("\n", 1)[0]:
        return "tsv"
    raise ConvertError(
        f"{path}: could not auto-detect the transcript format. Supported "
        f"inputs: {', '.join(PARSE_FORMATS)}."
    )


def parse_to_segments(path: str) -> list[dict]:
    """Parse a transcript file into the universal segment list.

    Auto-detects the format by extension then content. Returns a list of
    ``{start, end, text, ...}`` dicts (possibly empty for a header-only or
    cue-less file). Raises :class:`ConvertError` for an unreadable file, an
    unsupported / undetectable format, or a ``.txt`` input (output-only).
    """
    if not path or not os.path.isfile(path):
        raise ConvertError(f"Input file not found: {path!r}")

    ext = Path(path).suffix.lower().lstrip(".")
    if ext == "otr":
        try:
            return _parse_otr(path)
        except (OSError, ValueError) as e:
            raise ConvertError(f"Could not import .otr {path}: {e}") from e

    try:
        # utf-8-sig tolerates a BOM written by external editors (matches the
        # otranscribe / writers read paths).
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except (OSError, ValueError) as e:
        raise ConvertError(f"Could not read {path}: {e}") from e

    fmt = _detect_format(path, text)
    if fmt == "json":
        return _parse_json(text, path)
    if fmt in ("srt", "vtt"):
        return _parse_cue_format(text, path)
    if fmt == "tsv":
        return _parse_tsv(text, path)
    # _detect_format only returns members of PARSE_FORMATS; otr handled above.
    raise ConvertError(f"{path}: unsupported input format {fmt!r}.")


def _default_out_path(in_path: str, out_format: str) -> str:
    base = os.path.splitext(in_path)[0]
    return f"{base}.{out_format.lower()}"


def _same_file(a: str, b: str) -> bool:
    """True if *a* and *b* name the same file.

    Uses ``os.path.realpath`` (collapses symlinks / short names) plus
    ``os.path.normcase`` so a case-only difference — e.g. ``Movie.SRT``
    vs ``Movie.srt`` on Windows' case-insensitive filesystem — is treated
    as the same file. A plain ``abspath`` string compare misses that and
    would let the converter overwrite the source in place.
    """
    return (
        os.path.normcase(os.path.realpath(a))
        == os.path.normcase(os.path.realpath(b))
    )


def convert_file(
    in_path: str, out_format: str, out_path: str | None = None
) -> str:
    """Convert *in_path* to *out_format*, writing beside the input by default.

    Parses *in_path* into segments (the faster-whisper JSON middle format) then
    emits *out_format* via the matching ``core.writers`` text writer. Returns
    the path written. When *out_path* is None the output is written next to the
    input with the new extension; if that would overwrite the input itself
    (e.g. re-emitting an .srt as .srt in place) the path is suffixed with
    ``.converted`` to avoid clobbering the source.

    Raises :class:`ConvertError` for an unknown target format or a parse
    failure, and lets the writer's own ``OSError`` surface on a write failure.
    """
    fmt = (out_format or "").lower().lstrip(".")
    if fmt not in _writers.WRITERS:
        raise ConvertError(
            f"Unknown / non-text output format {out_format!r}. "
            f"Choose one of: {', '.join(OUTPUT_FORMATS)}."
        )

    segments = parse_to_segments(in_path)

    target = out_path or _default_out_path(in_path, fmt)
    if _same_file(target, in_path):
        base, ext = os.path.splitext(target)
        target = f"{base}.converted{ext}"

    body = _writers.get_writer(fmt)(segments, in_path)
    parent = os.path.dirname(os.path.abspath(target))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(body)
    return target
