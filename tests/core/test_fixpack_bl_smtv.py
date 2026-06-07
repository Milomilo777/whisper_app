"""Backlog fix-pack regression tests for core/integrations/smtv.py.

Hermetic: no Tk root, no network, no Whisper model. The SmtvEpisode is
built directly from in-memory data so nothing is fetched.

Covers the macOS-report finding that the CDN-encoded basename (taken
verbatim from the page's ``?file=`` value, which is attacker-
influenceable) bypassed ``_sanitise_filename`` in both ``filename_for``
and ``transcript_filename``. An NTFS alternate-data-stream colon or a
Windows reserved device stem (CON/PRN/AUX/NUL/COM#/LPT#) could therefore
reach ``os.path.join`` downstream unguarded.
"""
from __future__ import annotations

from core.integrations import smtv


def _episode_with_file(relative_path: str, quality: str = "1080p") -> smtv.SmtvEpisode:
    """Build an episode whose CDN download URL encodes ``relative_path``.

    Mirrors how ``_extract_videofiles`` constructs ``download_url`` so the
    CDN-basename code path in ``filename_for`` / ``transcript_filename`` is
    exercised exactly as in production.
    """
    download_url = smtv._CDN_PREFIX + smtv.urllib.parse.quote(relative_path, safe="/")
    return smtv.SmtvEpisode(
        vid="999900000001",
        title="Some Title",
        page_url="https://suprememastertv.com/en1/v/999900000001.html",
        lang_prefix="en",
        files=[smtv.SmtvFile(quality=quality, relative_path=relative_path,
                             download_url=download_url)],
    )


def test_filename_for_sanitises_ads_colon_in_cdn_basename():
    ep = _episode_with_file("vod/video/2026/evil:$DATA.mp4")
    name = smtv.filename_for(ep, "video-best")
    assert ":" not in name
    assert name == "evil_$DATA.mp4"


def test_filename_for_sanitises_reserved_device_stem_in_cdn_basename():
    ep = _episode_with_file("vod/video/2026/CON.mp4")
    name = smtv.filename_for(ep, "video-best")
    assert name.split(".", 1)[0].upper() not in smtv._WINDOWS_RESERVED_NAMES
    assert name == "_CON.mp4"


def test_filename_for_leaves_normal_cdn_basename_untouched():
    ep = _episode_with_file("vod/video/2026/9999-BMD1_1080p.mp4")
    assert smtv.filename_for(ep, "video-best") == "9999-BMD1_1080p.mp4"


def test_filename_for_audio_basename_is_sanitised():
    ep = _episode_with_file("vod/audio/2026/PRN.mp3", quality="audio")
    name = smtv.filename_for(ep, "audio")
    assert name == "_PRN.mp3"


def test_transcript_filename_sanitises_ads_colon():
    ep = _episode_with_file("vod/audio/2026/talk:stream.mp3", quality="audio")
    name = smtv.transcript_filename(ep)
    assert ":" not in name
    assert name == "talk_stream.txt"


def test_transcript_filename_sanitises_reserved_device_stem():
    ep = _episode_with_file("vod/audio/2026/NUL.mp3", quality="audio")
    name = smtv.transcript_filename(ep)
    assert name.split(".", 1)[0].upper() not in smtv._WINDOWS_RESERVED_NAMES
    assert name == "_NUL.txt"


def test_transcript_filename_leaves_normal_basename_untouched():
    ep = _episode_with_file("vod/audio/2026/9999-BMD1_audio.mp3", quality="audio")
    assert smtv.transcript_filename(ep) == "9999-BMD1_audio.txt"
