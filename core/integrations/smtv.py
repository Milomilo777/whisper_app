"""Supreme Master TV episode scraper — slim basic-edition port.

The site exposes per-episode video / audio URLs via a JS
``videoPlayerData`` global and a transcript inside
``<div class="article-text">``. We recognise SMTV URLs, fetch the
page over HTTPS (stdlib urllib), extract qualities + mp3 +
transcript + sibling-parts playlist, and download the chosen
variant. Defaults to mp3 (audio only — that's all the transcribe
pipeline needs). Time-range slicing isn't supported (CDN has no
server-side seek); :func:`download` logs one WARN and proceeds.
"""
from __future__ import annotations

import html as _html
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Callable

logger = logging.getLogger(__name__)

SMTV_HOST_RE = re.compile(
    r"^https?://(?:[a-z0-9-]+\.)*(?:suprememastertv\.com|smtv\.bot)/", re.I,
)
SMTV_EPISODE_RE = re.compile(
    r"^https?://(?:www\.)?suprememastertv\.com/"
    r"([a-z]{2,3})1/v/(\d{6,})\.html$", re.I,
)
_VIDEOFILE_RE = re.compile(
    r"""videoPlayerData\[\s*["']videoFile["']\s*\]\.push\(\s*new\s+Array\(\s*"""
    r"""['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]\s*\)\s*\)""",
)
_ARTICLE_TITLE_RE = re.compile(
    r'<h1[^>]*id="article-title"[^>]*>(.*?)</h1>', re.S,
)
_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.S)
_ARTICLE_TEXT_RE = re.compile(
    r'<div\s+class="article-text"\s+id="article-text">(.*?)</div>'
    r'(?=\s*(?:<div[^>]*class="article-thumb"|</div>\s*</div>\s*</div>\s*</article>))',
    re.S,
)
_PLAYLIST_MARKER_RE = re.compile(r'<div\s+[^>]*class="playlist-contaner"', re.I)
_PLAYLIST_END_RE = re.compile(r'<footer\b|id="footer"', re.I)
_PLAYLIST_ANCHOR_RE = re.compile(
    r'<a\s+[^>]*?href="\.\./v/(\d+)\.html"[^>]*?title="([^"]+)"',
)
_PART_RE = re.compile(r"\bPart\s+(\d+)\s+of\s+(\d+)\b", re.I)
_CDN_PREFIX = "https://cf-vdo.suprememastertv.com/vod/video/download-mp4.php?file="
_DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WhisperProject"
_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class SmtvError(RuntimeError):
    """Raised when an SMTV page can't be parsed or fetched."""


@dataclass(frozen=True)
class SmtvFile:
    quality: str
    relative_path: str
    download_url: str


@dataclass(frozen=True)
class SmtvSibling:
    url: str
    title: str
    part: int | None
    total: int | None


@dataclass(frozen=True)
class SmtvEpisode:
    vid: str
    title: str
    page_url: str
    lang_prefix: str
    files: list[SmtvFile] = field(default_factory=list)
    transcript_text: str = ""
    siblings: list[SmtvSibling] = field(default_factory=list)


def is_smtv_url(url: str) -> bool:
    """True for any URL on the SMTV host."""
    return bool(url) and bool(SMTV_HOST_RE.match(url.strip()))


def parse_episode_id(url: str) -> tuple[str, str] | None:
    """Return ``(lang_prefix, vid)`` for an SMTV episode URL or None."""
    m = SMTV_EPISODE_RE.match((url or "").strip())
    return (m.group(1).lower(), m.group(2)) if m else None


def fetch_episode(url: str, *, timeout: float = 30.0) -> SmtvEpisode:
    """HTTPS GET, parse, return an SmtvEpisode.

    Raises SmtvError on any failure shape so callers only need one
    except clause.
    """
    page_url = (url or "").strip()
    parsed_id = parse_episode_id(page_url)
    if parsed_id is None:
        raise SmtvError(f"not an SMTV episode URL: {page_url!r}")
    lang_prefix, vid = parsed_id
    html_text = _http_get(page_url, timeout=timeout)
    files = _extract_videofiles(html_text)
    if not files:
        raise SmtvError(
            "could not find videoPlayerData['videoFile'] entries on the "
            f"page — the site layout may have changed: {page_url}",
        )
    return SmtvEpisode(
        vid=vid, title=_extract_title(html_text) or vid,
        page_url=page_url, lang_prefix=lang_prefix, files=files,
        transcript_text=_extract_transcript_text(html_text),
        siblings=_extract_siblings(html_text, page_url),
    )


def parse_episode_page(url: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Plain-dict wrapper around :func:`fetch_episode` (title /
    qualities (non-audio) / mp3_url / transcript_text / siblings)."""
    ep = fetch_episode(url, timeout=timeout)
    return {
        "title": ep.title,
        "qualities": [f.quality for f in ep.files if f.quality != "audio"],
        "mp3_url": next(
            (f.download_url for f in ep.files if f.quality == "audio"), None,
        ),
        "transcript_text": ep.transcript_text,
        "siblings": [
            {"url": s.url, "title": s.title, "part": s.part, "total": s.total}
            for s in ep.siblings
        ],
    }


_QUALITY_MAP = {
    "video-max": "max", "video-1080": "1080p",
    "video-720": "720p", "video-396": "396p",
}


def best_url_for_mode(episode: SmtvEpisode, mode: str) -> str:
    """Return the CDN URL for ``mode`` — ``audio`` / ``video-best`` /
    ``video-1080`` / ``video-720`` / ``video-396``."""
    by_q = {f.quality: f.download_url for f in episode.files}
    if not mode:
        raise SmtvError("empty mode")
    if mode == "audio":
        if "audio" in by_q:
            return by_q["audio"]
        raise SmtvError(f"no audio track for episode {episode.vid}")
    if mode == "video-best":
        for want in ("max", "1080p", "720p", "396p"):
            if want in by_q:
                return by_q[want]
        for f in episode.files:
            if f.quality and f.quality.endswith("p"):
                return f.download_url
        raise SmtvError(f"no video file for episode {episode.vid}")
    if mode in _QUALITY_MAP:
        want = _QUALITY_MAP[mode]
        if want in by_q:
            return by_q[want]
        raise SmtvError(f"{want} not available for episode {episode.vid}")
    raise SmtvError(f"unknown mode: {mode!r}")


def filename_for(episode: SmtvEpisode, mode: str) -> str:
    """Suggested basename for the file at ``mode``."""
    base = _basename_from_cdn_url(best_url_for_mode(episode, mode))
    if base:
        return base
    return _sanitise_filename(episode.title) + (
        ".mp3" if mode == "audio" else ".mp4"
    )


def download(
    url: str, folder: str, *,
    video_quality: str = "audio",
    progress_cb: Callable[[float], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    timeout: float = 60.0,
    section_start: float | None = None,
    section_end: float | None = None,
) -> str:
    """Download one SMTV episode and return the saved absolute path.

    ``video_quality`` defaults to ``"audio"`` (mp3). Pass ``video-best``
    / ``video-720`` etc. for video. ``section_start`` / ``section_end``
    are ignored (SMTV has no server-side seek) and emit one WARN.
    """
    if section_start is not None or section_end is not None:
        warn_time_range_unsupported(url)
    episode = fetch_episode(url, timeout=timeout)
    cdn_url = best_url_for_mode(episode, video_quality)
    basename = _basename_from_cdn_url(cdn_url) or filename_for(
        episode, video_quality,
    )
    os.makedirs(folder, exist_ok=True)
    target_path = os.path.abspath(os.path.join(folder, basename))
    part_path = target_path + ".part"
    try:
        _stream_to_file(
            cdn_url, part_path,
            progress_cb=progress_cb, cancel_cb=cancel_cb, timeout=timeout,
        )
    except Exception:
        _quiet_unlink(part_path)
        raise
    if cancel_cb is not None and cancel_cb():
        _quiet_unlink(part_path)
        raise SmtvError("download cancelled")
    try:
        os.replace(part_path, target_path)
    except OSError as e:
        raise SmtvError(
            f"could not finalise download to {target_path}: {e}",
        ) from e
    _maybe_write_transcript(episode, folder, basename)
    return target_path


def _maybe_write_transcript(
    episode: SmtvEpisode, folder: str, basename: str,
) -> None:
    transcript = (episode.transcript_text or "").strip()
    if not transcript:
        return
    stem, _ = os.path.splitext(basename)
    path = os.path.join(folder, stem + ".txt")
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(transcript + "\n")
    except OSError as e:
        logger.warning("Could not write SMTV transcript %s: %s", path, e)


def warn_time_range_unsupported(url: str) -> None:
    """Log a single WARN: SMTV ignores time-range slicing."""
    logger.warning(
        "Time-range download not supported for SMTV URLs in this release; "
        "downloading the full clip. (url=%s)", url,
    )


def _http_get(url: str, *, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _DEFAULT_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        raise SmtvError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise SmtvError(f"network error fetching {url}: {e.reason}") from e
    except TimeoutError as e:
        raise SmtvError(f"timeout fetching {url} after {timeout}s") from e
    except OSError as e:
        # Catches ConnectionResetError + bare-OSError socket fails.
        raise SmtvError(f"network error fetching {url}: {e}") from e


def _emit_progress(
    cb: Callable[[float], None] | None, pct: float,
) -> None:
    if cb is None:
        return
    try:
        cb(pct)
    except Exception:  # noqa: BLE001
        logger.exception("SMTV progress_cb raised")


def _stream_to_file(
    url: str, dest_path: str, *,
    progress_cb: Callable[[float], None] | None,
    cancel_cb: Callable[[], bool] | None,
    timeout: float,
) -> None:
    import time as _time
    req = urllib.request.Request(url, headers={"User-Agent": _DEFAULT_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = _content_length_or_none(resp)
            downloaded = 0
            last_emit = 0.0
            with open(dest_path, "wb") as out:
                while True:
                    if cancel_cb is not None and cancel_cb():
                        return
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    now = _time.monotonic()
                    if total and (now - last_emit) >= 0.5:
                        _emit_progress(progress_cb, (downloaded / total) * 100.0)
                        last_emit = now
            if total:
                _emit_progress(progress_cb, 100.0)
    except urllib.error.HTTPError as e:
        raise SmtvError(f"SMTV CDN HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise SmtvError(f"SMTV CDN network error: {e.reason}") from e
    except TimeoutError as e:
        raise SmtvError("SMTV CDN read timeout") from e


def _content_length_or_none(resp: Any) -> int | None:
    raw = resp.headers.get("Content-Length") if resp.headers else None
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _quiet_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _extract_videofiles(html_text: str) -> list[SmtvFile]:
    seen: set[tuple[str, str]] = set()
    out: list[SmtvFile] = []
    for m in _VIDEOFILE_RE.finditer(html_text):
        key = (m.group(1), m.group(2))
        if key in seen:
            continue
        seen.add(key)
        out.append(SmtvFile(
            quality=key[0], relative_path=key[1],
            download_url=_CDN_PREFIX + urllib.parse.quote(key[1], safe="/"),
        ))
    return out


def _extract_title(html_text: str) -> str:
    m = _ARTICLE_TITLE_RE.search(html_text)
    if m:
        return _strip_tags(m.group(1)).strip()
    m = _TITLE_TAG_RE.search(html_text)
    if not m:
        return ""
    raw = _strip_tags(m.group(1)).strip()
    for sep in (" - Supreme Master Television", " | Supreme Master Television"):
        if raw.endswith(sep):
            return raw[:-len(sep)].strip()
    return raw


def _extract_transcript_text(html_text: str) -> str:
    m = _ARTICLE_TEXT_RE.search(html_text)
    return _strip_tags(m.group(1).strip()).strip() if m else ""


def _extract_siblings(html_text: str, page_url: str) -> list[SmtvSibling]:
    marker = _PLAYLIST_MARKER_RE.search(html_text)
    if not marker:
        return []
    end_match = _PLAYLIST_END_RE.search(html_text, marker.end())
    region = (
        html_text[marker.end():end_match.start()]
        if end_match else html_text[marker.end():]
    )
    my_id = parse_episode_id(page_url)
    my_vid = my_id[1] if my_id else None
    my_lang = my_id[0] if my_id else "en"
    # First pass: pin series prefix + total-parts from this episode's
    # own anchor in the playlist, used to filter the siblings below.
    self_total: int | None = None
    self_prefix: str | None = None
    for m in _PLAYLIST_ANCHOR_RE.finditer(region):
        if m.group(1) != my_vid:
            continue
        title = _html.unescape(m.group(2)).strip()
        _, self_total = _parse_part(title)
        self_prefix = _title_prefix_before_part(title)
        break
    seen: set[str] = set()
    candidates: list[tuple[int, SmtvSibling]] = []
    for m in _PLAYLIST_ANCHOR_RE.finditer(region):
        sib_vid = m.group(1)
        if sib_vid == my_vid or sib_vid in seen:
            continue
        title = _html.unescape(m.group(2)).strip()
        part, total = _parse_part(title)
        if self_total is not None and total is not None and total != self_total:
            continue
        if self_prefix and not title.startswith(self_prefix):
            continue
        seen.add(sib_vid)
        candidates.append((
            part if part is not None else 10**9,
            SmtvSibling(
                url=f"https://suprememastertv.com/{my_lang}1/v/{sib_vid}.html",
                title=title, part=part, total=total,
            ),
        ))
    candidates.sort(key=lambda kv: kv[0])
    return [sib for _, sib in candidates]


def _parse_part(title: str) -> tuple[int | None, int | None]:
    m = _PART_RE.search(title)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _title_prefix_before_part(title: str) -> str | None:
    m = _PART_RE.search(title)
    return title[: m.start()].rstrip(", ").strip() if m else None


def _basename_from_cdn_url(url: str) -> str | None:
    files = urllib.parse.parse_qs(
        urllib.parse.urlparse(url).query,
    ).get("file") or []
    return os.path.basename(files[0]) if files else None


_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)},
)


def _sanitise_filename(name: str) -> str:
    cleaned = re.sub(
        r"\s+", " ",
        _UNSAFE_FILENAME_CHARS.sub("_", name).strip().strip("."),
    )[:180].rstrip()
    if not cleaned:
        return "smtv_episode"
    # Avoid Windows reserved device names (CON / PRN / COM1 / LPT9 / ...).
    if cleaned.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        cleaned = "_" + cleaned
    return cleaned


class _TextStripper(HTMLParser):
    """Minimal HTML → text: ``<br>``/``<p>``/``<div>``/``<li>`` insert
    line breaks; everything else is unwrapped."""

    _BLOCK_CLOSE = frozenset({"p", "div", "br", "li"})

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[Any]) -> None:
        if tag == "br":
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_CLOSE:
            self._chunks.append("\n\n")

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def handle_entityref(self, name: str) -> None:
        self._chunks.append(_html.unescape("&" + name + ";"))

    def handle_charref(self, name: str) -> None:
        self._chunks.append(_html.unescape("&#" + name + ";"))

    def value(self) -> str:
        # Collapse runs of blank lines so the output reads naturally.
        out: list[str] = []
        prev_blank = False
        for raw in "".join(self._chunks).split("\n"):
            line = raw.rstrip()
            if line:
                out.append(line)
                prev_blank = False
            elif not prev_blank:
                out.append("")
                prev_blank = True
        return "\n".join(out).strip()


def _strip_tags(html_text: str) -> str:
    parser = _TextStripper()
    parser.feed(html_text)
    parser.close()
    return parser.value()
