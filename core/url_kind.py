"""Classify a URL as ``"smtv"`` / ``"yt-dlp"`` / ``"unsupported"``.

The Download Videos section calls :func:`url_kind` once per pasted
URL and routes the work accordingly:

  * ``smtv``        → :mod:`core.integrations.smtv` direct CDN stream
  * ``yt-dlp``      → bundled ``bin/yt-dlp.exe`` subprocess
  * ``unsupported`` → reject up front with a friendly message

The classifier is deliberately strict at the top and forgiving at the
bottom: anything that *looks* like an HTTP(S) URL but isn't SMTV is
handed to yt-dlp, because yt-dlp's extractor list is enormous and
trying to maintain our own allow-list would be a losing battle.
``file://``, ``javascript:``, blank strings, and anything missing a
host fall through to ``unsupported``.
"""
from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

UrlKind = Literal["smtv", "yt-dlp", "unsupported"]

__all__ = ["url_kind", "UrlKind"]


# Matches ``suprememastertv.com`` (with or without ``www.``) and the
# short bot mirror ``smtv.bot``. Both subdomains and the bare host
# are accepted.
_SMTV_HOST_RE = re.compile(
    r"^(?:[a-z0-9-]+\.)*(?:suprememastertv\.com|smtv\.bot)$",
    re.I,
)


def url_kind(url: str) -> UrlKind:
    """Return the dispatcher key for ``url``."""
    if not isinstance(url, str):
        return "unsupported"
    candidate = url.strip()
    if not candidate:
        return "unsupported"

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return "unsupported"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return "unsupported"
    host = (parsed.hostname or "").lower()
    if not host:
        return "unsupported"

    if _SMTV_HOST_RE.match(host):
        return "smtv"

    # Anything else with a host and at least a path or a query goes to
    # yt-dlp. Bare ``https://example.com/`` is still acceptable — many
    # extractors take a channel root URL.
    return "yt-dlp"
