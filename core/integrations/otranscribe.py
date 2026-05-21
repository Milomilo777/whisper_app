"""oTranscribe (.otr) bidirectional file-format converter.

Public API (exactly four names):

    fmt_otr_time(seconds) -> str          # display format M:SS or H:MM:SS
    srt_to_otr(srt_path, media_filename=...) -> str
    whisper_json_to_otr(json_path, media_filename=...) -> str
    otr_to_srt(otr_path) -> str

Everything else in this module is private.

The .otr format is documented in docs/integrations/otranscribe-research.md.
The contract for end-time inference in otr_to_srt: for all but the last
segment, end = next segment's start. For the last segment,
end = max(media_time, start + 5.0).

Stdlib only (json, html, html.parser, re, pathlib).
"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

__all__ = ["fmt_otr_time", "srt_to_otr", "whisper_json_to_otr", "otr_to_srt"]

NBSP = " "


def fmt_otr_time(seconds: float) -> str:
    """oTranscribe display format. < 1 hour: 'M:SS'. >= 1 hour: 'H:MM:SS'.

    No zero-padding on the leading hour or minute, two-digit minutes/seconds
    elsewhere. Matches src/js/app/timestamps.js in the oTranscribe repo.
    """
    s = int(seconds) if seconds is not None else 0
    if s < 0:
        s = 0
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h:
        return f"{h}:{m:02}:{sec:02}"
    return f"{m}:{sec:02}"


def _fmt_srt_time(seconds: float) -> str:
    total_ms = int(round((seconds or 0.0) * 1000))
    if total_ms < 0:
        total_ms = 0
    h = total_ms // 3_600_000
    m = (total_ms % 3_600_000) // 60_000
    s = (total_ms % 60_000) // 1000
    ms = total_ms % 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


_SRT_TS = re.compile(
    r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
)


def _parse_srt(text: str):
    """Yield (start_seconds, end_seconds, body) tuples from SRT text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return
    blocks = re.split(r"\n\s*\n+", text)
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if len(lines) < 2:
            continue
        ts_idx = None
        for i, ln in enumerate(lines):
            if "-->" in ln:
                ts_idx = i
                break
        if ts_idx is None:
            continue
        m = _SRT_TS.search(lines[ts_idx])
        if not m:
            continue
        start = (
            int(m.group(1)) * 3600
            + int(m.group(2)) * 60
            + int(m.group(3))
            + int(m.group(4)) / 1000.0
        )
        end = (
            int(m.group(5)) * 3600
            + int(m.group(6)) * 60
            + int(m.group(7))
            + int(m.group(8)) / 1000.0
        )
        body_lines = lines[ts_idx + 1 :]
        body = " ".join(ln.strip() for ln in body_lines).strip()
        if body:
            yield (start, end, body)


def _segments_to_otr_string(
    segments, media_filename: str = "", media_time: float = 0.0
) -> str:
    """Build the .otr JSON string from a sequence of (start, end, body)."""
    paragraphs = []
    for start, _end, body in segments:
        ts = f"{float(start):.3f}"
        display = fmt_otr_time(float(start))
        body_html = html.escape(body or "")
        paragraphs.append(
            f'<p><span class="timestamp" contenteditable="false" '
            f'data-timestamp="{ts}">{display}</span>{NBSP}{body_html}</p>'
        )
    text_html = "".join(paragraphs).replace("\n", " ").replace("\r", " ")
    payload = {
        "text": text_html,
        "media": Path(media_filename).name if media_filename else "",
        "media-source": "",
        "media-time": float(media_time or 0.0),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def srt_to_otr(srt_path: str, media_filename: str = "") -> str:
    """Read an SRT file at *srt_path*, return its .otr JSON as a string.

    The output is UTF-8 safe (``ensure_ascii=False``). Pass *media_filename*
    so the .otr's "media" field shows the source filename's basename in
    oTranscribe; only the basename is used.
    """
    with open(srt_path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    segments = list(_parse_srt(text))
    return _segments_to_otr_string(segments, media_filename)


def whisper_json_to_otr(json_path: str, media_filename: str = "") -> str:
    """Read this app's JSON output (a list of {start, end, text} dicts) at
    *json_path* and return the .otr JSON string. Same output schema as
    ``srt_to_otr``.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array of segments at {json_path}; got {type(data).__name__}"
        )
    segments = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        start = float(entry.get("start", 0.0))
        end = float(entry.get("end", start))
        body = (entry.get("text") or "").strip()
        if body:
            segments.append((start, end, body))
    return _segments_to_otr_string(segments, media_filename)


class _OtrParser(HTMLParser):
    """Walk an .otr text HTML payload into a list of (start_seconds, body)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.segments: list[tuple[float, str]] = []
        self._current_start = None  # type: float | None
        self._buffer: list[str] = []
        self._in_timestamp = False

    def _flush(self) -> None:
        if self._current_start is None:
            return
        body = "".join(self._buffer).strip().lstrip(NBSP + " \t").strip()
        self.segments.append((self._current_start, body))
        self._current_start = None
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        if tag == "span":
            attrs_dict = dict(attrs)
            if attrs_dict.get("class") == "timestamp":
                self._flush()
                ts_raw = attrs_dict.get("data-timestamp") or "0"
                try:
                    self._current_start = float(ts_raw)
                except (TypeError, ValueError):
                    self._current_start = 0.0
                self._in_timestamp = True
        # Any other tag inside body keeps adding text via handle_data.

    def handle_endtag(self, tag):
        if tag == "span" and self._in_timestamp:
            self._in_timestamp = False
        elif tag == "p":
            self._flush()

    def handle_startendtag(self, tag, attrs):
        # Self-closing tags inside the body — ignore.
        pass

    def handle_data(self, data):
        if self._current_start is None or self._in_timestamp:
            return
        self._buffer.append(data)

    def finalize(self):
        self._flush()


def otr_to_srt(otr_path: str) -> str:
    """Read an .otr file at *otr_path* and return SRT text.

    End times are inferred:
      * for all but the last segment, end = next segment's start;
      * for the last segment, end = max(media_time, start + 5.0).
    """
    with open(otr_path, "r", encoding="utf-8-sig") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"{otr_path} is not a JSON object")
    text_html = payload.get("text") or ""
    media_time = float(payload.get("media-time") or 0.0)

    parser = _OtrParser()
    parser.feed(text_html)
    parser.finalize()
    segments = [(s, b) for s, b in parser.segments if b]

    out_lines = []
    for i, (start, body) in enumerate(segments):
        if i + 1 < len(segments):
            end = segments[i + 1][0]
        else:
            end = max(media_time, start + 5.0)
        if end <= start:
            end = start + 5.0
        out_lines.append(
            f"{i + 1}\n{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n{body}\n"
        )
    return "\n".join(out_lines)
