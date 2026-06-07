"""Regression: the LAN server's result-download Content-Disposition header
must stay latin-1 encodable even when the output filename has non-ASCII
characters (the SMTV .docx template name carries an en-dash). Before the fix,
http.server's latin-1 header encoding raised UnicodeEncodeError mid-response
and the client saw RemoteDisconnected — the SMTV format was un-downloadable
over the network. Found by a live end-to-end server test.
"""
from __future__ import annotations

import urllib.parse

from core.server.httpd import content_disposition_attachment


# The exact shape the SMTV docx writer produces (en-dash U+2013).
SMTV_NAME = "clip30 -Transcription in English – Translation in English.docx"


def test_header_is_latin1_encodable_for_non_ascii_name():
    """The crux of the bug: the header value MUST encode as latin-1 (that is
    what http.server does) without raising."""
    value = content_disposition_attachment(SMTV_NAME)
    # Must not raise — this is exactly what crashed the handler before.
    value.encode("latin-1")


def test_header_carries_rfc6266_utf8_name_and_ascii_fallback():
    value = content_disposition_attachment(SMTV_NAME)
    # RFC 6266 UTF-8 form present with the percent-encoded real name.
    assert "filename*=UTF-8''" in value
    assert urllib.parse.quote(SMTV_NAME, safe="") in value
    # An ASCII fallback filename="..." is also present (en-dash -> placeholder).
    assert 'filename="' in value
    assert "–" not in value  # the raw en-dash never appears in the header


def test_plain_ascii_name_round_trips():
    value = content_disposition_attachment("clip30.srt")
    assert 'filename="clip30.srt"' in value
    value.encode("latin-1")  # still safe


def test_header_strips_crlf_injection():
    value = content_disposition_attachment('a"b\r\nX-Evil: 1.docx')
    assert "\r" not in value and "\n" not in value
    # the embedded quote must not survive in the ASCII fallback token
    assert 'filename="a_b' in value
    value.encode("latin-1")


def test_empty_name_falls_back():
    value = content_disposition_attachment("")
    assert 'filename="download"' in value
    value.encode("latin-1")
