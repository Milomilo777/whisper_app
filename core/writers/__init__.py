"""Format writers for transcribed segments.

Each module exposes ``write(segments, audio_path) -> str`` returning the file
body. Segments are dicts with at least ``{start, end, text}`` and optionally
``{words: [{start, end, word, probability}, ...]}``.

Use :func:`get_writer` to look up a writer by short format name.
"""
from __future__ import annotations

from typing import Callable

from . import json_writer, lrc, srt, tsv, txt, vtt

WriterFn = Callable[[list[dict], str], str]

WRITERS: dict[str, WriterFn] = {
    "srt": srt.write,
    "vtt": vtt.write,
    "tsv": tsv.write,
    "txt": txt.write,
    "json": json_writer.write,
    "lrc": lrc.write,
}


def get_writer(name: str) -> WriterFn:
    """Look up a writer by short format name; raises ``KeyError`` if unknown."""
    return WRITERS[name.lower()]


def supported_formats() -> list[str]:
    return sorted(WRITERS.keys())
