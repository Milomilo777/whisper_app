"""Tests for the pure builders + parsers in ``app.services.download_service``."""
from __future__ import annotations

import json
import types

import pytest

from app.services.download_service import (
    build_download_command,
    build_subtitle_command,
    parse_destination_line,
    parse_progress_line,
)


def _task(folder: str = "/tmp/out", url: str = "https://www.youtube.com/watch?v=abc",
          mode: str = "Audio and video", output: str = "mp4",
          audio_kind: str = "best_audio", audio_id: str = "140",
          video_kind: str = "best_video", video_id: str = "137"):
    return types.SimpleNamespace(
        folder=folder,
        url=url,
        format_info={
            "mode": mode,
            "output": output,
            "audio": {"kind": audio_kind, "format_id": audio_id},
            "video": {"kind": video_kind, "format_id": video_id},
        },
    )


def test_build_subtitle_command_passes_lang_and_output():
    task = _task()
    cmd = build_subtitle_command(task, "en", yt_dlp_path="ytdlp.exe", bin_path="C:/bin")
    assert cmd[0] == "ytdlp.exe"
    assert "--ffmpeg-location" in cmd and cmd[cmd.index("--ffmpeg-location") + 1] == "C:/bin"
    assert "--write-auto-subs" in cmd and "--write-subs" in cmd
    assert "--sub-langs" in cmd and cmd[cmd.index("--sub-langs") + 1] == "en"
    assert "--no-playlist" in cmd
    assert cmd[-1] == task.url


def test_build_subtitle_command_normalizes_lang_list():
    task = _task()
    cmd = build_subtitle_command(task, " en , ja ", yt_dlp_path="ytdlp.exe", bin_path="C:/bin")
    assert cmd[cmd.index("--sub-langs") + 1] == "en,ja"


def test_build_download_command_audio_only_uses_x_flag():
    task = _task(mode="Audio", output="mp3", audio_kind="best_audio")
    cmd = build_download_command(task, yt_dlp_path="ytdlp", bin_path="bin")
    assert "-x" in cmd
    assert "--audio-format" in cmd and cmd[cmd.index("--audio-format") + 1] == "mp3"
    assert "--merge-output-format" not in cmd


def test_build_download_command_audio_only_specific_format_id():
    task = _task(mode="Audio", output="m4a", audio_kind="specific", audio_id="251")
    cmd = build_download_command(task, yt_dlp_path="ytdlp", bin_path="bin")
    f_idx = cmd.index("-f")
    assert cmd[f_idx + 1] == "251"


def test_build_download_command_video_uses_merge_output_format():
    task = _task(mode="Audio and video", output="mp4")
    cmd = build_download_command(task, yt_dlp_path="ytdlp", bin_path="bin")
    assert "--merge-output-format" in cmd
    assert cmd[cmd.index("--merge-output-format") + 1] == "mp4"
    f = cmd[cmd.index("-f") + 1]
    assert "+" in f


def test_build_download_command_video_picks_mp4_friendly_selectors_for_mp4_output():
    task = _task(output="mp4")
    cmd = build_download_command(task, yt_dlp_path="ytdlp", bin_path="bin")
    f = cmd[cmd.index("-f") + 1]
    assert "ext=mp4" in f


def test_build_download_command_video_uses_neutral_selectors_for_webm():
    task = _task(output="webm")
    cmd = build_download_command(task, yt_dlp_path="ytdlp", bin_path="bin")
    f = cmd[cmd.index("-f") + 1]
    assert "ext=mp4" not in f


def test_build_download_command_supports_progress_template():
    task = _task()
    cmd = build_download_command(
        task, yt_dlp_path="ytdlp", bin_path="bin", progress_template="%(progress)j"
    )
    assert "--progress-template" in cmd
    assert cmd[cmd.index("--progress-template") + 1] == "%(progress)j"


def test_build_download_command_supports_sponsorblock_categories():
    task = _task()
    cmd = build_download_command(
        task,
        yt_dlp_path="ytdlp",
        bin_path="bin",
        sponsorblock_categories=["sponsor", "intro", "outro"],
    )
    assert "--sponsorblock-remove" in cmd
    assert cmd[cmd.index("--sponsorblock-remove") + 1] == "sponsor,intro,outro"


def test_build_download_command_no_sponsorblock_when_categories_empty():
    task = _task()
    cmd = build_download_command(task, yt_dlp_path="ytdlp", bin_path="bin", sponsorblock_categories=[])
    assert "--sponsorblock-remove" not in cmd


def test_build_download_command_url_is_last():
    task = _task()
    cmd = build_download_command(task, yt_dlp_path="ytdlp", bin_path="bin")
    assert cmd[-1] == task.url


# --- parse_progress_line ----------------------------------------------------


def test_parse_progress_line_legacy_percent():
    parsed = parse_progress_line("[download]   42.7% of 100MiB at 1MiB/s ETA 00:34")
    assert parsed and parsed["percent"] == pytest.approx(42.7)


def test_parse_progress_line_json_percent_derived():
    payload = {"downloaded_bytes": 5000, "total_bytes": 10000, "speed": 1234}
    parsed = parse_progress_line(json.dumps(payload))
    assert parsed and parsed["percent"] == pytest.approx(50.0)
    assert parsed["downloaded_bytes"] == 5000


def test_parse_progress_line_json_uses_total_bytes_estimate_when_no_total():
    payload = {"downloaded_bytes": 250, "total_bytes_estimate": 1000}
    parsed = parse_progress_line(json.dumps(payload))
    assert parsed and parsed["percent"] == pytest.approx(25.0)


def test_parse_progress_line_returns_none_for_unknown():
    assert parse_progress_line("just a log line") is None
    assert parse_progress_line("") is None
    assert parse_progress_line("{not json}") is None


def test_parse_progress_line_caps_at_100():
    parsed = parse_progress_line(json.dumps({"downloaded_bytes": 999, "total_bytes": 100}))
    assert parsed and parsed["percent"] == 100.0


# --- parse_destination_line ------------------------------------------------


def test_parse_destination_line_picks_path():
    line = "[download] Destination: C:/out/My Video.mp4"
    assert parse_destination_line(line) == "C:/out/My Video.mp4"


def test_parse_destination_line_handles_merger():
    line = "[Merger] Merging formats into: /tmp/out.mp4"
    assert parse_destination_line(line) == "/tmp/out.mp4"


def test_parse_destination_line_handles_extract_audio():
    line = "[ExtractAudio] Destination: /tmp/song.mp3"
    assert parse_destination_line(line) == "/tmp/song.mp3"


def test_parse_destination_line_returns_none_for_other_lines():
    assert parse_destination_line("[download] 42% of 10MB") is None
    assert parse_destination_line("") is None
