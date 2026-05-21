"""Format writers for transcribed segments.

Each text writer exposes ``write(segments, audio_path) -> str``
returning the file body. Segments are dicts with at least
``{start, end, text}`` and optionally
``{words: [{start, end, word, probability}, ...], speaker: "Speaker 1"}``.

The ``docx`` writer is binary; it exposes ``write_bytes(segments,
audio_path) -> bytes`` instead. ``BINARY_WRITERS`` carries the
binary set so callers know whether to use ``"wb"`` mode.

Use :func:`get_writer` for text writers, :func:`get_binary_writer`
for binary writers, and :func:`is_binary` to disambiguate.
"""
from __future__ import annotations

from typing import Callable

from . import docx_writer, json_writer, lrc, md, pdf_writer, srt, tsv, txt, vtt

WriterFn = Callable[[list[dict], str], str]
BinaryWriterFn = Callable[[list[dict], str], bytes]

WRITERS: dict[str, WriterFn] = {
    "srt": srt.write,
    "vtt": vtt.write,
    "tsv": tsv.write,
    "txt": txt.write,
    "json": json_writer.write,
    "lrc": lrc.write,
    "md": md.write,
}

BINARY_WRITERS: dict[str, BinaryWriterFn] = {
    "docx": docx_writer.write_bytes,
    "pdf": pdf_writer.write_bytes,
}


def get_writer(name: str) -> WriterFn:
    """Look up a text writer by short format name; raises ``KeyError`` if unknown."""
    return WRITERS[name.lower()]


def get_binary_writer(name: str) -> BinaryWriterFn:
    """Look up a binary writer by short format name; raises ``KeyError`` if unknown."""
    return BINARY_WRITERS[name.lower()]


def is_binary(name: str) -> bool:
    """True iff the named format must be written in binary mode."""
    return name.lower() in BINARY_WRITERS


def supported_formats() -> list[str]:
    return sorted(list(WRITERS.keys()) + list(BINARY_WRITERS.keys()))
