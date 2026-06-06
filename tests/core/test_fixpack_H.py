"""Regression tests for fixpack cluster H (core/integrations/smtv.py).

Cluster H fixes one bug:

  * A valid SMTV episode URL that carries a ``?query`` string or a
    ``#fragment`` was not recognised as an episode. ``parse_episode_id``
    returned ``None`` (the path regex was anchored with ``.html$``), so
    the URL fell through to the yt-dlp probe, which rejects SMTV URLs.

These tests are fully hermetic: no real Tk root, no network, no real
model/binaries. The fetch path is exercised with a stubbed
``urllib.request.urlopen``, mirroring the existing
``tests/integrations/test_smtv.py`` pattern.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.integrations import smtv


# ----------------------------------------------- query / fragment tolerance --


@pytest.mark.parametrize(
    "url, expected",
    [
        # plain link still works (no regression)
        (
            "https://suprememastertv.com/en1/v/314924375480.html",
            ("en", "314924375480"),
        ),
        # trailing query string (autoplay / tracking params)
        (
            "https://suprememastertv.com/en1/v/314924375480.html?autoplay=1",
            ("en", "314924375480"),
        ),
        # trailing fragment (browser-appended anchor)
        (
            "https://suprememastertv.com/en1/v/314924375480.html#top",
            ("en", "314924375480"),
        ),
        # both query and fragment
        (
            "https://suprememastertv.com/fa1/v/999900000007.html?utm=x#frag",
            ("fa", "999900000007"),
        ),
        # www. host + query
        (
            "https://www.suprememastertv.com/de1/v/123456789.html?ref=share",
            ("de", "123456789"),
        ),
        # surrounding whitespace + query (pasted links often have it)
        (
            "  https://suprememastertv.com/en1/v/314924375480.html?a=1  ",
            ("en", "314924375480"),
        ),
        # empty query / fragment markers
        (
            "https://suprememastertv.com/en1/v/314924375480.html?",
            ("en", "314924375480"),
        ),
        (
            "https://suprememastertv.com/en1/v/314924375480.html#",
            ("en", "314924375480"),
        ),
    ],
)
def test_parse_episode_id_accepts_query_and_fragment(url, expected):
    assert smtv.parse_episode_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        # extra path chars right after .html must NOT match (no separator)
        "https://suprememastertv.com/en1/v/314924375480.htmlxyz",
        "https://suprememastertv.com/en1/v/314924375480.html.bak",
        # non-episode pages remain rejected
        "https://suprememastertv.com/en1/search/",
        "https://suprememastertv.com/en1/",
        # wrong host
        "https://example.com/en1/v/314924375480.html?autoplay=1",
        # not a URL at all
        "not an SMTV URL",
        "",
    ],
)
def test_parse_episode_id_still_rejects_non_episodes(url):
    assert smtv.parse_episode_id(url) is None


def test_is_smtv_url_and_parse_agree_on_query_links():
    """The two helpers must agree for a real episode link with a query:
    host-match True AND episode-match non-None. The bug was the mismatch
    (host True, episode None) that routed the URL to yt-dlp."""
    url = "https://suprememastertv.com/en1/v/314924375480.html?autoplay=1"
    assert smtv.is_smtv_url(url) is True
    assert smtv.parse_episode_id(url) is not None


# ----------------------------------------------------- fetch path (stubbed) --


_MINIMAL_EPISODE_HTML = (
    "<html><head><title>Sample - Supreme Master Television</title></head>"
    "<body>"
    "<script>"
    "videoPlayerData['videoFile'].push(new Array('720p','vod/2026/x-720.mp4'));"
    "</script>"
    "</body></html>"
)


def _make_urlopen_returning(text: str, captured: list[str]):
    def _open(req, timeout=None):
        # Record exactly what URL fetch_episode handed to urllib so we can
        # assert the query string is preserved through to the HTTP GET.
        captured.append(getattr(req, "full_url", req))

        class _R:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *_a):
                return False

            def read(self_inner):
                return text.encode("utf-8")

            class headers:
                @staticmethod
                def get_content_charset(default=None):
                    return "utf-8"

        return _R()

    return _open


def test_fetch_episode_accepts_query_url_and_preserves_it():
    captured: list[str] = []
    url = "https://suprememastertv.com/en1/v/999900000001.html?autoplay=1"
    with patch(
        "core.integrations.smtv.urllib.request.urlopen",
        _make_urlopen_returning(_MINIMAL_EPISODE_HTML, captured),
    ):
        ep = smtv.fetch_episode(url)

    # Recognised as an episode (would have raised SmtvError before the fix).
    assert ep.vid == "999900000001"
    assert ep.lang_prefix == "en"
    assert [f.quality for f in ep.files] == ["720p"]
    # The query string is carried through to the actual HTTP GET.
    assert captured == [url]


def test_fetch_episode_still_rejects_non_episode_url():
    with pytest.raises(smtv.SmtvError):
        smtv.fetch_episode("https://suprememastertv.com/en1/search/")
