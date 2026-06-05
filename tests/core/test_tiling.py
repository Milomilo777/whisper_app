"""Tests for the Video Tiling engine's pure logic (no ffplay/yt-dlp run).

Hermetic: every test here exercises a pure function or a controller method
that does no I/O. The engine's run-loop, subprocess spawning, and the Tk UI
are intentionally NOT exercised (they need real binaries / a display).
"""
from __future__ import annotations

from core import tiling


# --- divisions clamping ----------------------------------------------------
def test_clamp_divisions_bounds():
    assert tiling._clamp_divisions(0) == tiling.MIN_DIVISIONS
    assert tiling._clamp_divisions(999) == tiling.MAX_DIVISIONS
    assert tiling._clamp_divisions(3) == 3
    assert tiling._clamp_divisions("bad") == 3  # type: ignore[arg-type]


def test_public_clamp_divisions():
    assert tiling.clamp_divisions(0) == 1
    assert tiling.clamp_divisions(100) == 64
    assert tiling.clamp_divisions(None) == 3  # type: ignore[arg-type]
    assert tiling.clamp_divisions(5) == 5


# --- tile filter -----------------------------------------------------------
def test_build_tile_filter_shape():
    f = tiling.build_tile_filter(4)
    assert "tile=4x4" in f
    assert "fps=source_fps*4*4" in f


# --- command builders ------------------------------------------------------
def test_build_commands_yt_dlp_has_end_of_options_before_url():
    yt, fp = tiling.build_commands("yt-dlp", "ffplay", "https://x/stream", 3)
    # URL is last and guarded by "--" so a "-"-prefixed URL can't inject a flag.
    assert yt[-1] == "https://x/stream"
    assert yt[-2] == "--"
    assert "-o" in yt and "-" in yt
    # ffplay reads stdin, applies the tile filter, fullscreen.
    assert fp[0] == "ffplay"
    assert "-vf" in fp and "tile=3x3" in " ".join(fp)
    assert fp[-2:] == ["-i", "-"]


def test_build_commands_respects_explicit_format():
    yt, _ = tiling.build_commands("yt-dlp", "ffplay", "https://u", 2,
                                  fmt="best[height<=720]")
    assert "best[height<=720]" in yt
    # Explicit fmt still goes through the robust extractor flags + "--" guard.
    assert "--extractor-args" in yt
    assert yt[-2] == "--" and yt[-1] == "https://u"


def test_build_yt_dlp_command_player_clients_and_retries():
    cmd = tiling.build_yt_dlp_command("yt-dlp", "https://u", 3, "Auto")
    assert cmd[0] == "yt-dlp"
    joined = " ".join(cmd)
    # Robust extraction: multiple player clients, retries, socket timeout.
    assert "youtube:player_client=" + tiling.YT_PLAYER_CLIENTS in joined
    assert "--retries" in cmd and "--socket-timeout" in cmd
    # URL after "--", streamed to stdout.
    assert cmd[-2] == "--" and cmd[-1] == "https://u"
    assert "-o" in cmd


# --- format selection ------------------------------------------------------
def test_select_format_manual_quality_bands():
    for q, h in [("1080p", 1080), ("720p", 720), ("480p", 480),
                 ("360p", 360), ("240p", 240), ("144p", 144)]:
        sel = tiling.select_format(q, 3)
        assert "best[height<={}]".format(h) in sel
        assert sel.endswith("/best")


def test_select_format_auto_lowers_with_density():
    # Auto picks resolution from grid density (boundaries from the reference).
    assert "height<=1080" in tiling.select_format("Auto", 1)
    assert "height<=1080" in tiling.select_format("Auto", 2)
    assert "height<=720" in tiling.select_format("Auto", 3)
    assert "height<=720" in tiling.select_format("Auto", 4)
    assert "height<=360" in tiling.select_format("Auto", 5)
    assert "height<=360" in tiling.select_format("Auto", 17)
    assert "height<=240" in tiling.select_format("Auto", 18)
    assert "height<=240" in tiling.select_format("Auto", 35)
    assert "height<=144" in tiling.select_format("Auto", 36)
    assert "height<=144" in tiling.select_format("Auto", 64)


def test_select_format_unknown_quality_is_auto():
    # An unrecognised quality string falls back to the Auto bands.
    assert tiling.select_format("nonsense", 1) == tiling.select_format("Auto", 1)
    assert tiling.select_format(None, 10) == tiling.select_format("Auto", 10)


# --- backoff ---------------------------------------------------------------
def test_next_backoff_doubles_and_caps():
    assert tiling.next_backoff(3) == 6
    assert tiling.next_backoff(6) == 12
    assert tiling.next_backoff(20) == 30  # capped at 30
    assert tiling.next_backoff(30) == 30
    assert tiling.next_backoff(3, cap=10) == 6
    assert tiling.next_backoff(8, cap=10) == 10


# --- URL validation (injection hardening) ----------------------------------
def test_is_valid_stream_url():
    assert tiling.is_valid_stream_url("http://a/b")
    assert tiling.is_valid_stream_url("https://a/b")
    assert tiling.is_valid_stream_url("  HTTPS://A/B  ")  # trimmed + case
    # Rejected: non-http schemes, a "-"-prefixed injection, junk, non-str.
    assert not tiling.is_valid_stream_url("ftp://a/b")
    assert not tiling.is_valid_stream_url("--exec=rm")
    assert not tiling.is_valid_stream_url("-f")
    assert not tiling.is_valid_stream_url("file:///etc/passwd")
    assert not tiling.is_valid_stream_url("")
    assert not tiling.is_valid_stream_url(None)  # type: ignore[arg-type]
    assert not tiling.is_valid_stream_url(123)  # type: ignore[arg-type]


# --- pip-install detection (self-heal gating) ------------------------------
def test_looks_like_pip_ytdlp():
    assert tiling._looks_like_pip_ytdlp("Please use pip to update")
    assert tiling._looks_like_pip_ytdlp("update via your package manager")
    assert tiling._looks_like_pip_ytdlp("you installed yt-dlp with pip")
    # Must NOT false-match a bare 'pip' inside an unrelated word/message.
    assert not tiling._looks_like_pip_ytdlp("broken pipe")
    assert not tiling._looks_like_pip_ytdlp("Updated yt-dlp to nightly")
    assert not tiling._looks_like_pip_ytdlp("")
    assert not tiling._looks_like_pip_ytdlp(None)


# --- ffplay availability ---------------------------------------------------
def test_ffplay_available_returns_bool():
    assert isinstance(tiling.ffplay_available(), bool)


# --- controller surface (no spawn) -----------------------------------------
def test_controller_idle_and_stop_is_safe():
    c = tiling.TilingController()
    assert c.is_running() is False
    c.stop()  # must not raise when nothing is running
    assert c.is_running() is False


def test_start_blank_url_raises_runtime():
    c = tiling.TilingController()
    try:
        c.start("   ", 3)
    except RuntimeError:
        return
    except FileNotFoundError:
        raise AssertionError(
            "blank URL should raise RuntimeError before the ffplay check"
        )
    raise AssertionError("expected RuntimeError for a blank URL")


def test_start_non_http_url_raises_runtime():
    c = tiling.TilingController()
    try:
        c.start("ftp://evil/-injection", 3)
    except RuntimeError:
        return
    except FileNotFoundError:
        raise AssertionError(
            "a non-http URL should raise RuntimeError before the ffplay check"
        )
    raise AssertionError("expected RuntimeError for a non-http URL")


def test_yt_dlp_argv_uses_explicit_fmt_over_quality():
    """An explicit fmt passed to start() wins over the quality band."""
    c = tiling.TilingController()
    c._url = "https://u"
    c._divisions = 3
    c._explicit_fmt = "best[height<=480]"
    c._quality = "1080p"
    argv = c._yt_dlp_argv("yt-dlp")
    assert "best[height<=480]" in argv
    assert "best[height<=1080]" not in " ".join(argv)
    assert argv[-2] == "--" and argv[-1] == "https://u"


def test_yt_dlp_argv_uses_quality_band_when_no_fmt():
    c = tiling.TilingController()
    c._url = "https://u"
    c._divisions = 3
    c._explicit_fmt = None
    c._quality = "720p"
    argv = c._yt_dlp_argv("yt-dlp")
    assert "best[height<=720]" in " ".join(argv)
