"""Tests for the Tk-free monitor-detection + tiling-geometry helpers.

Hermetic: monkeypatches the screeninfo / Win32 probes so nothing touches a
real display. Pure-function tests need no patching at all.
"""
from __future__ import annotations

import sys
import types

from core import monitors


# --- list_monitors ordering / indexing / fallback --------------------------
def _fake_screeninfo(raw):
    """Build a fake `screeninfo` module whose get_monitors() returns `raw`."""
    mod = types.ModuleType("screeninfo")

    def get_monitors():
        return raw

    mod.get_monitors = get_monitors  # type: ignore[attr-defined]
    return mod


class _M:
    def __init__(self, x, y, w, h, name="", primary=False):
        self.x, self.y, self.width, self.height = x, y, w, h
        self.name, self.is_primary = name, primary


def test_list_monitors_sorted_left_to_right_and_indexed(monkeypatch):
    # Provide three monitors out of x-order; expect left-to-right sort + index.
    raw = [
        _M(1920, 0, 1920, 1080, "B"),
        _M(0, 0, 1920, 1080, "A", primary=True),
        _M(3840, 0, 1280, 720, "C"),
    ]
    monkeypatch.setitem(sys.modules, "screeninfo", _fake_screeninfo(raw))
    mons = monitors.list_monitors()
    assert [m["x"] for m in mons] == [0, 1920, 3840]
    assert [m["index"] for m in mons] == [0, 1, 2]
    assert [m["name"] for m in mons] == ["A", "B", "C"]
    assert mons[0]["is_primary"] is True


def test_list_monitors_blank_names_get_display_label(monkeypatch):
    raw = [_M(0, 0, 1920, 1080, "")]
    monkeypatch.setitem(sys.modules, "screeninfo", _fake_screeninfo(raw))
    mons = monitors.list_monitors()
    assert mons[0]["name"] == "Display 1"


def test_list_monitors_screeninfo_raises_falls_back(monkeypatch):
    """When screeninfo.get_monitors() RAISES (headless/RDP/hotplug) and the
    Win32 probe is also unavailable, fall back to a single 1920x1080 monitor."""
    mod = types.ModuleType("screeninfo")

    def boom():
        raise RuntimeError("ScreenInfoError: no display")

    mod.get_monitors = boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "screeninfo", mod)
    # Force the Win32 fallback to report nothing so we reach the single fallback.
    monkeypatch.setattr(monitors, "_from_win32", lambda: [])
    mons = monitors.list_monitors()
    assert len(mons) == 1
    assert mons[0]["width"] == 1920 and mons[0]["height"] == 1080
    assert mons[0]["index"] == 0
    assert mons[0]["is_primary"] is True


def test_list_monitors_screeninfo_absent_uses_win32(monkeypatch):
    """screeninfo not installed -> the ctypes Win32 path supplies monitors."""
    monkeypatch.setitem(
        sys.modules, "screeninfo", None
    )  # import raises -> _from_screeninfo() returns []
    monkeypatch.setattr(
        monitors, "_from_win32",
        lambda: [{"x": 0, "y": 0, "width": 2560, "height": 1440,
                  "name": "", "is_primary": True}],
    )
    mons = monitors.list_monitors()
    assert len(mons) == 1
    assert mons[0]["width"] == 2560


# --- primary_index ---------------------------------------------------------
def test_primary_index_prefers_flagged_then_leftmost():
    mons = [
        monitors.Monitor(index=0, x=0, y=0, width=1920, height=1080,
                         name="A", is_primary=False),
        monitors.Monitor(index=1, x=1920, y=0, width=1920, height=1080,
                         name="B", is_primary=True),
    ]
    assert monitors.primary_index(mons) == 1
    # No primary flag anywhere -> the left-most (first after sort) index.
    mons[1] = monitors.Monitor(index=1, x=1920, y=0, width=1920, height=1080,
                               name="B", is_primary=False)
    assert monitors.primary_index(mons) == 0


# --- select_monitors -------------------------------------------------------
def _three():
    return [
        monitors.Monitor(index=0, x=0, y=0, width=1920, height=1080,
                         name="A", is_primary=True),
        monitors.Monitor(index=1, x=1920, y=0, width=1920, height=1080,
                         name="B", is_primary=False),
        monitors.Monitor(index=2, x=3840, y=0, width=1280, height=720,
                         name="C", is_primary=False),
    ]


def test_select_monitors_single_default_is_primary():
    mons = _three()
    chosen = monitors.select_monitors(mons, [], multi_monitor=False)
    assert [m["index"] for m in chosen] == [0]


def test_select_monitors_single_honours_first_ticked():
    mons = _three()
    chosen = monitors.select_monitors(mons, [2, 1], multi_monitor=False)
    # Single mode returns just ONE monitor: the first ticked that exists.
    assert [m["index"] for m in chosen] == [2]


def test_select_monitors_multi_subset():
    mons = _three()
    chosen = monitors.select_monitors(mons, [0, 2], multi_monitor=True)
    assert [m["index"] for m in chosen] == [0, 2]


def test_select_monitors_multi_none_ticked_uses_all():
    mons = _three()
    chosen = monitors.select_monitors(mons, [], multi_monitor=True)
    assert [m["index"] for m in chosen] == [0, 1, 2]


def test_select_monitors_ignores_stale_indices():
    mons = _three()
    # A saved index that no longer exists is dropped; in multi mode an empty
    # result then falls back to all monitors.
    chosen = monitors.select_monitors(mons, [99], multi_monitor=True)
    assert [m["index"] for m in chosen] == [0, 1, 2]
    # Single mode with only stale indices falls back to the primary.
    chosen1 = monitors.select_monitors(mons, [99], multi_monitor=False)
    assert [m["index"] for m in chosen1] == [0]


# --- tile_filter_for -------------------------------------------------------
def test_tile_filter_for_even_tiles_and_output_dims():
    vf, ow, oh = monitors.tile_filter_for(1920, 1080, 3)
    # fps*N^2 method, NxN tile.
    assert "fps=source_fps*9" in vf
    assert "tile=3x3" in vf
    # Tile size floored to even; output = exact NxN multiple that fits.
    # 1920//3 = 640 (even), 1080//3 = 360 (even).
    assert "scale=w=640:h=360" in vf
    assert (ow, oh) == (1920, 1080)


def test_tile_filter_for_floors_to_even():
    # 1366//3 = 455 -> floored to 454 (even); 768//3 = 256 (even).
    vf, ow, oh = monitors.tile_filter_for(1366, 768, 3)
    assert "scale=w=454:h=256" in vf
    assert (ow, oh) == (454 * 3, 256 * 3)


def test_tile_filter_for_n1_is_full_frame():
    vf, ow, oh = monitors.tile_filter_for(1920, 1080, 1)
    assert "tile=1x1" in vf
    assert "fps=source_fps*1" in vf
    assert (ow, oh) == (1920, 1080)


# --- window_opts_for -------------------------------------------------------
def test_window_opts_for_places_borderless_window():
    mon = monitors.Monitor(index=1, x=1920, y=0, width=1920, height=1080,
                           name="B", is_primary=False)
    opts = monitors.window_opts_for(mon, 1920, 1080)
    assert "-noborder" in opts
    assert "-alwaysontop" in opts
    assert opts[opts.index("-left") + 1] == "1920"
    assert opts[opts.index("-top") + 1] == "0"
    assert opts[opts.index("-x") + 1] == "1920"
    assert opts[opts.index("-y") + 1] == "1080"


def test_window_opts_for_no_always_on_top():
    mon = monitors.Monitor(index=0, x=0, y=0, width=800, height=600,
                           name="A", is_primary=True)
    opts = monitors.window_opts_for(mon, 800, 600, always_on_top=False)
    assert "-alwaysontop" not in opts
    assert "-noborder" in opts


# --- describe --------------------------------------------------------------
def test_describe_labels_and_primary_tag():
    mon = monitors.Monitor(index=0, x=0, y=0, width=1920, height=1080,
                           name="A", is_primary=True)
    s = monitors.describe(mon)
    assert "Monitor 1" in s
    assert "1920x1080" in s
    assert "(0,0)" in s
    assert "[primary]" in s
    mon2 = monitors.Monitor(index=1, x=1920, y=0, width=1280, height=720,
                            name="B", is_primary=False)
    assert "[primary]" not in monitors.describe(mon2)
