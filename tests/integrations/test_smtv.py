"""Unit tests for core/integrations/smtv.py.

Covers URL recognition, page parsing, sibling filtering, transcript
extraction, filename construction, and the unavailable-mode error
case. The live-network smoke test lives separately under
``tests/smoke/test_smtv_smoke.py`` so this suite stays hermetic.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core.integrations import smtv


FIXTURES = Path(__file__).parent / "fixtures"
FULL_EPISODE_FIXTURE = FIXTURES / "smtv_episode_full.html"
NEWSCLIP_FIXTURE = FIXTURES / "smtv_episode_newsclip.html"
NO_VIDEODATA_FIXTURE = FIXTURES / "smtv_episode_no_videodata.html"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# -------------------------------------------------------------- URL helpers --


def test_is_smtv_url_accepts_english_episode():
    assert smtv.is_smtv_url("https://suprememastertv.com/en1/v/314924375480.html")


def test_is_smtv_url_accepts_other_languages():
    for lang in ("fa", "de", "ch", "gb", "kr"):
        assert smtv.is_smtv_url(f"https://suprememastertv.com/{lang}1/v/123456789.html")


def test_is_smtv_url_rejects_other_hosts():
    for url in [
        "https://example.com/v/123.html",
        "https://youtube.com/watch?v=abc",
        "",
        "  ",
        "not a url",
    ]:
        assert not smtv.is_smtv_url(url)


def test_parse_episode_id_extracts_lang_and_vid():
    assert smtv.parse_episode_id(
        "https://suprememastertv.com/en1/v/314924375480.html"
    ) == ("en", "314924375480")
    assert smtv.parse_episode_id(
        "https://www.suprememastertv.com/fa1/v/999900000007.html"
    ) == ("fa", "999900000007")


def test_parse_episode_id_returns_none_for_search_root():
    assert smtv.parse_episode_id("https://suprememastertv.com/en1/search/") is None
    assert smtv.parse_episode_id("https://suprememastertv.com/en1/") is None
    assert smtv.parse_episode_id("not an SMTV URL") is None


# ---------------------------------------------------------------- parser ----


def _make_urlopen_returning(text: str):
    def _open(req, timeout=None):
        class _R:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *_a):
                return False

            def read(self_inner):
                return text.encode("utf-8")

            class headers:  # match urllib's HTTPResponse.headers interface
                @staticmethod
                def get_content_charset(default=None):
                    return "utf-8"

        return _R()

    return _open


def test_fetch_episode_extracts_all_fields():
    html_text = _load(FULL_EPISODE_FIXTURE)
    with patch("core.integrations.smtv.urllib.request.urlopen",
               _make_urlopen_returning(html_text)):
        ep = smtv.fetch_episode("https://suprememastertv.com/en1/v/999900000001.html")

    assert ep.vid == "999900000001"
    assert ep.lang_prefix == "en"
    assert "Test Episode" in ep.title
    assert ep.youtube_id == "AbCdEf01234"
    assert ep.duration_seconds == 37 * 60 + 31
    assert ep.poster_url is not None and "9999-BMD1.jpg" in ep.poster_url


def test_fetch_episode_extracts_four_files_with_audio():
    html_text = _load(FULL_EPISODE_FIXTURE)
    with patch("core.integrations.smtv.urllib.request.urlopen",
               _make_urlopen_returning(html_text)):
        ep = smtv.fetch_episode("https://suprememastertv.com/en1/v/999900000001.html")

    qualities = [f.quality for f in ep.files]
    assert qualities == ["1080p", "720p", "396p", "audio"]
    for f in ep.files:
        assert f.download_url.startswith(
            "https://cf-vdo.suprememastertv.com/vod/video/download-mp4.php?file="
        )


def test_fetch_episode_newsclip_has_no_audio():
    html_text = _load(NEWSCLIP_FIXTURE)
    with patch("core.integrations.smtv.urllib.request.urlopen",
               _make_urlopen_returning(html_text)):
        ep = smtv.fetch_episode("https://suprememastertv.com/en1/v/314951825753.html")

    qualities = [f.quality for f in ep.files]
    assert qualities == ["720p", "396p"]
    assert ep.duration_seconds == 3 * 60 + 36


def test_fetch_episode_raises_on_missing_videofile():
    html_text = _load(NO_VIDEODATA_FIXTURE)
    with patch("core.integrations.smtv.urllib.request.urlopen",
               _make_urlopen_returning(html_text)):
        with pytest.raises(smtv.SmtvError):
            smtv.fetch_episode("https://suprememastertv.com/en1/v/777700000000.html")


def test_fetch_episode_rejects_non_episode_url():
    with pytest.raises(smtv.SmtvError):
        smtv.fetch_episode("https://suprememastertv.com/en1/search/")


def test_fetch_episode_siblings_only_series_match():
    html_text = _load(FULL_EPISODE_FIXTURE)
    with patch("core.integrations.smtv.urllib.request.urlopen",
               _make_urlopen_returning(html_text)):
        ep = smtv.fetch_episode("https://suprememastertv.com/en1/v/999900000001.html")

    # Fixture has 9 anchors total: 7 same series + 2 unrelated. The
    # current episode is excluded, so we expect parts 2..7 = 6 siblings.
    assert len(ep.siblings) == 6
    assert [s.part for s in ep.siblings] == [2, 3, 4, 5, 6, 7]
    assert all(s.total == 7 for s in ep.siblings)
    assert all("Test Episode" in s.title for s in ep.siblings)


def test_fetch_episode_sibling_url_uses_page_language_prefix():
    html_text = _load(FULL_EPISODE_FIXTURE)
    # Substitute the canonical English URL with a Persian one; the
    # fixture content is unchanged, only the page_url passed in. The
    # sibling URLs should adopt /fa1/.
    with patch("core.integrations.smtv.urllib.request.urlopen",
               _make_urlopen_returning(html_text)):
        ep = smtv.fetch_episode("https://suprememastertv.com/fa1/v/999900000001.html")

    assert ep.lang_prefix == "fa"
    for s in ep.siblings:
        assert s.url.startswith("https://suprememastertv.com/fa1/v/"), s.url


def test_transcript_text_extracts_paragraphs():
    html_text = _load(FULL_EPISODE_FIXTURE)
    with patch("core.integrations.smtv.urllib.request.urlopen",
               _make_urlopen_returning(html_text)):
        ep = smtv.fetch_episode("https://suprememastertv.com/en1/v/999900000001.html")

    assert "experts at eating" in ep.transcript_text
    assert "second paragraph" in ep.transcript_text
    assert "<p>" not in ep.transcript_text


def test_transcript_empty_when_block_absent():
    html_text = _load(NEWSCLIP_FIXTURE)
    with patch("core.integrations.smtv.urllib.request.urlopen",
               _make_urlopen_returning(html_text)):
        ep = smtv.fetch_episode("https://suprememastertv.com/en1/v/314951825753.html")

    assert ep.transcript_text == ""
    assert ep.transcript_html == ""


# --------------------------------------------------- mode + filename APIs --


def _episode_from_fixture(path: Path, page_url: str) -> smtv.SmtvEpisode:
    text = _load(path)
    with patch("core.integrations.smtv.urllib.request.urlopen",
               _make_urlopen_returning(text)):
        return smtv.fetch_episode(page_url)


def test_best_url_for_mode_audio_present():
    ep = _episode_from_fixture(
        FULL_EPISODE_FIXTURE, "https://suprememastertv.com/en1/v/999900000001.html"
    )
    url = smtv.best_url_for_mode(ep, "audio")
    assert url.endswith("-p1o7.mp3")


def test_best_url_for_mode_audio_missing_raises():
    ep = _episode_from_fixture(
        NEWSCLIP_FIXTURE, "https://suprememastertv.com/en1/v/314951825753.html"
    )
    with pytest.raises(smtv.SmtvError):
        smtv.best_url_for_mode(ep, "audio")


def test_best_url_for_mode_video_best_prefers_1080():
    ep = _episode_from_fixture(
        FULL_EPISODE_FIXTURE, "https://suprememastertv.com/en1/v/999900000001.html"
    )
    url = smtv.best_url_for_mode(ep, "video-best")
    assert url.endswith("-1080p.mp4")


def test_best_url_for_mode_video_best_falls_back_to_720_for_newsclip():
    ep = _episode_from_fixture(
        NEWSCLIP_FIXTURE, "https://suprememastertv.com/en1/v/314951825753.html"
    )
    url = smtv.best_url_for_mode(ep, "video-best")
    assert url.endswith("-2m.mp4")


def test_best_url_for_mode_unknown_raises():
    ep = _episode_from_fixture(
        FULL_EPISODE_FIXTURE, "https://suprememastertv.com/en1/v/999900000001.html"
    )
    with pytest.raises(smtv.SmtvError):
        smtv.best_url_for_mode(ep, "bogus-mode")


def test_filename_for_uses_cdn_basename():
    ep = _episode_from_fixture(
        FULL_EPISODE_FIXTURE, "https://suprememastertv.com/en1/v/999900000001.html"
    )
    assert smtv.filename_for(ep, "video-720").endswith("-p1o7-2m.mp4")
    assert smtv.filename_for(ep, "audio").endswith("-p1o7.mp3")


def test_transcript_filename_mirrors_audio_base():
    ep = _episode_from_fixture(
        FULL_EPISODE_FIXTURE, "https://suprememastertv.com/en1/v/999900000001.html"
    )
    txt = smtv.transcript_filename(ep)
    assert txt.endswith(".txt")
    # Audio is "9999-BMD-20240101-Test-Episode-p1o7.mp3" → transcript
    # mirrors it with .txt
    assert "p1o7" in txt


def test_transcript_filename_falls_back_to_first_video_when_no_audio():
    ep = _episode_from_fixture(
        NEWSCLIP_FIXTURE, "https://suprememastertv.com/en1/v/314951825753.html"
    )
    txt = smtv.transcript_filename(ep)
    assert txt.endswith(".txt")
    assert "2m" in txt  # mirrors the 720p basename


def test_sanitise_filename_handles_unsafe_characters(monkeypatch):
    # Construct a minimal SmtvEpisode without going through fetch_episode
    ep = smtv.SmtvEpisode(
        vid="000000000001",
        title='evil: <name>? "with" bad/chars\\here',
        page_url="https://suprememastertv.com/en1/v/000000000001.html",
        lang_prefix="en",
        files=[],
    )
    # Direct call to the private sanitiser via best_url failing → use the
    # fact that filename_for falls back to title + ext when no CDN base.
    cleaned = smtv._sanitise_filename(ep.title)
    for bad in '<>:"/\\|?*':
        assert bad not in cleaned


# ------------------------------------ time-range slicing not supported (v1.0.3)


def test_warn_time_range_unsupported_logs_warning(caplog):
    """warn_time_range_unsupported emits exactly one WARN line."""
    import logging

    caplog.set_level(logging.WARNING, logger="core.integrations.smtv")
    smtv.warn_time_range_unsupported(
        "https://suprememastertv.com/en1/v/314324511501.html"
    )
    matching = [
        r for r in caplog.records
        if "Time-range download is not supported" in r.getMessage()
    ]
    assert len(matching) == 1
    assert matching[0].levelno == logging.WARNING
    assert "314324511501" in matching[0].getMessage()
