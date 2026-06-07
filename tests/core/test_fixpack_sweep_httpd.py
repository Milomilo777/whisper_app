"""Regression for the LAN server multipart parser's after-file field recovery.

Pins one boundary defect in the on-disk, streaming-friendly upload parser
``JobRequestHandler._extract_upload_from_file`` (a staticmethod that reads a
temp file in bounded windows — no socket, no network, no model):

The after-file TEXT fields (formats / language / options) are recovered from a
bounded TRAILING window only when the file part's END was located OUTSIDE the
leading head window. But a body can be laid out so the file part's body (and
its closing boundary) DOES fit inside the head window, while the small text
fields appended AFTER it spill past the head window edge — i.e. the head scan
sees ``file_end < len(head)`` yet the whole body did not fit (``len(head) <
size``). In that case the head scan drops the spilled fields (its header
terminator lies past the window), and the recovery was gated on
``file_end >= len(head)``, so it never ran. Result: the user's formats /
language choices were silently lost and the job fell back to ``["srt"]`` +
auto-detect.

The fix decouples the field recovery from the ``file_end``-in-head condition:
the bounded trailing-window field re-scan runs whenever the whole body did not
fit the head window (``len(head) < size``), regardless of where ``file_end``
landed.

Hermetic: a tiny synthetic body on a temp file with the window constants
monkeypatched small. No network, no model, no Tk root.
"""
from __future__ import annotations

import core.server.httpd as httpd_mod
from core.server.httpd import JobRequestHandler

_BOUNDARY = "----WhisperProjectSweepBnd"


def _multipart_body(payload: bytes) -> bytes:
    """One file part FIRST, then formats + language text parts, then close.

    Mirrors the order the server's own page (a browser ``FormData``) sends.
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
    return file_part + fmt_part + lang_part + closing


def test_after_file_fields_recovered_when_file_end_inside_head_window(
    tmp_path, monkeypatch,
):
    """Regression: fields spilling past the head window were dropped when the
    file part's END fit inside that window.

    The defect's signature: ``file_end < len(head)`` (so the file's closing
    boundary IS inside the head window) but ``len(head) < size`` (the trailing
    text fields are NOT). The pre-fix gate ``file_end >= len(head)`` skipped the
    recovery entirely, losing formats / language.
    """
    # File-part header up to and including the blank line that ends the headers.
    delim = b"--" + _BOUNDARY.encode("latin-1")
    file_header = (
        delim + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="clip.mp4"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
    )
    payload = b"P" * 40
    body = _multipart_body(payload)

    # file_end (end of payload) = start of payload + len(payload).
    file_body_start = len(file_header)
    file_end = file_body_start + len(payload)
    # The `formats` part starts right after the file body's trailing CRLF +
    # closing delimiter. Put the window edge a little past that delimiter but
    # before the `formats` header's terminating blank line, so the head scan
    # sees the file's closing boundary (=> file_end resolved inside head) yet
    # cannot parse the `formats` header (its \r\n\r\n is beyond the window).
    closing_delim_pos = file_end + len(b"\r\n")
    fmt_header_terminator = body.find(b"\r\n\r\n", closing_delim_pos)
    assert fmt_header_terminator != -1
    window = fmt_header_terminator - 1  # just shy of the formats header end
    assert file_end < window < len(body), (window, file_end, len(body))

    monkeypatch.setattr(httpd_mod, "_MULTIPART_HEADER_WINDOW", window)
    monkeypatch.setattr(httpd_mod, "_MULTIPART_TAIL_WINDOW", 64 * 1024)

    tmp = tmp_path / "u.part"
    tmp.write_bytes(body)
    fn, start, end, fields = JobRequestHandler._extract_upload_from_file(
        str(tmp), len(body), _BOUNDARY)

    assert fn == "clip.mp4"
    # The file payload stays byte-exact (the trailing text parts are not
    # swallowed into the media).
    assert body[start:end] == payload
    # The after-file text fields must be recovered, not silently dropped.
    assert fields.get("formats") == "srt,txt"
    assert fields.get("language") == "en"
