"""Tests for ``core.url_kind`` — URL classifier."""
from __future__ import annotations

import random

import pytest

from core.url_kind import url_kind


@pytest.mark.parametrize(
    "url",
    [
        "https://www.suprememastertv.com/en/cw/video/123",
        "https://suprememastertv.com/en/cw/video/456",
        "http://suprememastertv.com/x",
        "https://www.smtv.bot/v/789",
        "https://smtv.bot/x",
        "https://en.smtv.bot/path",
        "https://CDN.suprememastertv.com/test",
        "HTTPS://suprememastertv.com/x",
    ],
)
def test_url_kind_smtv(url: str) -> None:
    assert url_kind(url) == "smtv"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://youtube.com/shorts/xyz",
        "https://vimeo.com/12345",
        "https://www.twitch.tv/foo/v/123",
        "https://x.com/some/path",
        "https://example.com/",
        "http://example.com/path",
        "https://bilibili.com/video/abc",
    ],
)
def test_url_kind_yt_dlp(url: str) -> None:
    assert url_kind(url) == "yt-dlp"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        None,
        42,
        ["https://x.com"],
        "ftp://example.com/file.zip",
        "file:///tmp/x.mp4",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "mailto:user@example.com",
        "://malformed",
        "not-a-url-at-all",
        "https://",  # no host
        "https:///path-only",  # empty host
    ],
)
def test_url_kind_unsupported(url) -> None:
    assert url_kind(url) == "unsupported"


def test_url_kind_returns_literal_string() -> None:
    out = url_kind("https://x.com/y")
    assert out in {"smtv", "yt-dlp", "unsupported"}


def test_url_kind_strips_whitespace() -> None:
    assert url_kind("  https://youtube.com/x  ") == "yt-dlp"


@pytest.mark.parametrize(
    "smtv_url",
    [
        "https://suprememastertv.com",
        "https://www.suprememastertv.com",
        "https://en.suprememastertv.com",
        "https://www2.suprememastertv.com",
        "https://api.smtv.bot",
    ],
)
def test_url_kind_smtv_various_subdomains(smtv_url: str) -> None:
    assert url_kind(smtv_url) == "smtv"


def test_url_kind_smtv_lookalike_rejected() -> None:
    """A domain that contains 'suprememastertv' as substring but isn't
    the real host → yt-dlp (not smtv)."""
    assert url_kind("https://fakesuprememastertv.com") == "yt-dlp"


def test_url_kind_evil_smtv_subdomain_match_only_real() -> None:
    assert url_kind("https://malicioussmtv.bot.attacker.com/x") == "yt-dlp"


def test_url_kind_fuzz_random_strings_never_raises() -> None:
    """500 random strings → url_kind always returns one of the three labels."""
    rng = random.Random(123)
    chars = "abcdefghijklmnopqrstuvwxyz0123456789:/.?=&-_#"
    for _ in range(500):
        n = rng.randint(0, 100)
        s = "".join(rng.choice(chars) for _ in range(n))
        out = url_kind(s)
        assert out in {"smtv", "yt-dlp", "unsupported"}


def test_url_kind_non_string_inputs_unsupported() -> None:
    """Type-coerce paranoia."""
    for bad in (None, 0, 1.5, True, b"https://x.com", object()):
        assert url_kind(bad) == "unsupported"  # type: ignore[arg-type]


def test_url_kind_with_query_and_fragment() -> None:
    assert url_kind("https://youtube.com/watch?v=abc#t=10") == "yt-dlp"


def test_url_kind_with_port() -> None:
    assert url_kind("https://x.com:8443/path") == "yt-dlp"


def test_url_kind_with_basic_auth() -> None:
    assert url_kind("https://user:pass@example.com/path") == "yt-dlp"


def test_url_kind_smtv_with_query() -> None:
    assert url_kind("https://smtv.bot/v?id=1") == "smtv"
