"""Regression pack for the LAN server multipart streaming parser.

These exercise the on-disk, streaming-friendly upload parser
``JobRequestHandler._extract_upload_from_file`` (a staticmethod that reads a
temp file in bounded windows — no socket, no network, no model). They pin two
defects that bit EVERY real (multi-MB) upload sent by the server's own page,
which appends the ``file`` part FIRST and the small ``formats`` / ``language``
/ option text fields AFTER it (a browser ``FormData`` preserves append order):

  1. Those after-file text fields lay beyond the bounded leading window, so the
     parser dropped them silently — every real upload fell back to the default
     ``["srt"]`` format + auto-detect language, ignoring the user's choices.
  2. The file part's end was located with the LAST boundary in the trailing
     window, which swallowed the intervening text-field parts into the saved
     media as trailing junk bytes (the file was no longer byte-exact).

The parser keeps the whole payload on disk and only ever reads a small leading
window + a small trailing window, so these run with a tiny synthetic body and
do not buffer anything large.
"""
from __future__ import annotations

import os
import tempfile

from core.server.httpd import (
    _MULTIPART_HEADER_WINDOW,
    JobRequestHandler,
)

_BOUNDARY = "----WhisperProjectBoundary7e3f"


def _build_body(payload: bytes, fields_after_file: bool) -> bytes:
    """A multipart/form-data body: one file part + formats/language text parts.

    When ``fields_after_file`` the text parts come AFTER the file part (the
    order the server's own page sends); otherwise before it.
    """
    delim = b"--" + _BOUNDARY.encode("latin-1")
    file_part = (
        delim + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="clip.mp4"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + payload + b"\r\n"
    )
    fmt_part = (
        delim + b"\r\n"
        b'Content-Disposition: form-data; name="formats"\r\n\r\n'
        b"srt,txt\r\n"
    )
    lang_part = (
        delim + b"\r\n"
        b'Content-Disposition: form-data; name="language"\r\n\r\n'
        b"en\r\n"
    )
    closing = delim + b"--\r\n"
    if fields_after_file:
        return file_part + fmt_part + lang_part + closing
    return fmt_part + lang_part + file_part + closing


def _scan(body: bytes) -> tuple[str, int, int, dict[str, str], bytes]:
    """Run the on-disk parser over ``body`` and return its result + file bytes."""
    fd, tmp = tempfile.mkstemp(prefix="fixpack-upload-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        size = len(body)
        filename, file_start, file_end, fields = (
            JobRequestHandler._extract_upload_from_file(tmp, size, _BOUNDARY)
        )
        media = b""
        if file_start >= 0:
            with open(tmp, "rb") as f:
                f.seek(file_start)
                media = f.read(file_end - file_start)
        return filename, file_start, file_end, fields, media
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def test_text_fields_after_large_file_are_recovered():
    """Regression: formats/language placed AFTER a >window file were dropped.

    The server page appends the file first, so for any real upload the text
    fields sit beyond the bounded leading window. The parser must read the
    trailing window for them too.
    """
    payload = b"\xde\xad\xbe\xef" * ((_MULTIPART_HEADER_WINDOW // 4) + 4096)
    assert len(payload) > _MULTIPART_HEADER_WINDOW  # genuinely past the window
    filename, _start, _end, fields, _media = _scan(
        _build_body(payload, fields_after_file=True)
    )
    assert filename == "clip.mp4"
    assert fields.get("formats") == "srt,txt"
    assert fields.get("language") == "en"


def test_large_file_with_trailing_fields_is_byte_exact():
    """Regression: the saved media must equal the payload exactly.

    Locating the file end with the LAST boundary swallowed the trailing
    text-field parts into the media as junk bytes; the first boundary after
    the body is the correct end.
    """
    payload = bytes(range(256)) * ((_MULTIPART_HEADER_WINDOW // 256) + 2048)
    assert len(payload) > _MULTIPART_HEADER_WINDOW
    _filename, _start, _end, _fields, media = _scan(
        _build_body(payload, fields_after_file=True)
    )
    assert media == payload, (
        f"saved media not byte-exact: got {len(media)} bytes, "
        f"expected {len(payload)}"
    )


def test_large_file_as_last_part_is_byte_exact():
    """A file part that is the LAST part (no fields after) stays byte-exact."""
    payload = b"Y" * (_MULTIPART_HEADER_WINDOW + 4096)
    delim = b"--" + _BOUNDARY.encode("latin-1")
    body = (
        delim + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="b.mp4"\r\n\r\n'
        + payload + b"\r\n"
        + delim + b"--\r\n"
    )
    _filename, _start, _end, fields, media = _scan(body)
    assert media == payload
    assert fields == {}


def test_text_fields_before_file_still_work():
    """Fields BEFORE the file (inside the leading window) are unaffected."""
    payload = b"Z" * (_MULTIPART_HEADER_WINDOW + 1024)
    filename, _start, _end, fields, media = _scan(
        _build_body(payload, fields_after_file=False)
    )
    assert filename == "clip.mp4"
    assert media == payload
    assert fields.get("formats") == "srt,txt"
    assert fields.get("language") == "en"


def test_small_upload_with_trailing_fields_unchanged():
    """A small (sub-window) upload with trailing fields keeps working."""
    payload = b"hello world"
    filename, _start, _end, fields, media = _scan(
        _build_body(payload, fields_after_file=True)
    )
    assert filename == "clip.mp4"
    assert media == payload
    assert fields.get("formats") == "srt,txt"
    assert fields.get("language") == "en"
