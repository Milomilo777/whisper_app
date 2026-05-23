"""Format writers for transcribed segments.

Each writer exposes ``write(segments, audio_path) -> str`` returning
the file body. Segments are dicts with at least
``{start, end, text}``.

Basic edition: SRT + JSON + TXT only.
"""
from __future__ import annotations

from typing import Callable

from . import json_writer, srt, txt

WriterFn = Callable[[list[dict], str], str]

WRITERS: dict[str, WriterFn] = {
    "srt": srt.write,
    "json": json_writer.write,
    "txt": txt.write,
}


def get_writer(name: str) -> WriterFn:
    """Look up a writer by short format name; raises ``KeyError`` if unknown."""
    return WRITERS[name.lower()]


def supported_formats() -> list[str]:
    return sorted(WRITERS.keys())
