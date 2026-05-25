"""Tests for the Video Tiling command builder + controller (no ffplay run)."""
from __future__ import annotations

from core import tiling


def test_clamp_divisions_bounds():
    assert tiling._clamp_divisions(0) == tiling.MIN_DIVISIONS
    assert tiling._clamp_divisions(99) == tiling.MAX_DIVISIONS
    assert tiling._clamp_divisions(3) == 3
    assert tiling._clamp_divisions("bad") == 3  # type: ignore[arg-type]


def test_build_tile_filter_shape():
    f = tiling.build_tile_filter(4)
    assert "tile=4x4" in f
    assert "fps=source_fps*4*4" in f


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
    yt, _ = tiling.build_commands("yt-dlp", "ffplay", "u", 2, fmt="best[height<=720]")
    assert "best[height<=720]" in yt


def test_ffplay_available_returns_bool():
    assert isinstance(tiling.ffplay_available(), bool)


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
        # ffplay missing is also an acceptable early-exit on a CI box, but
        # a blank URL should be caught first.
        raise AssertionError("blank URL should raise RuntimeError before the ffplay check")
    raise AssertionError("expected RuntimeError for a blank URL")
