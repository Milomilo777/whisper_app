"""Tk-free multi-monitor detection + per-monitor tiling geometry.

Ported from the maintainer's standalone video-tiler (``monitor_utils.py``)
and adapted to this project's conventions: NO tkinter import (this runs in
``core`` alongside the transcription engine), and ``screeninfo`` is an
OPTIONAL dependency.

The playback design (see :mod:`core.tiling`) is one yt-dlp download fanned
out to one ffplay per selected monitor; each ffplay covers exactly one
physical monitor (which is reliable), instead of a single window trying to
span several monitors (which is not).

Detection order (each step degrades gracefully to the next):

  1. ``screeninfo.get_monitors()`` — preferred, cross-platform. Lazy-imported
     and wrapped in try/except because it can RAISE (headless / RDP / no
     display / a transient hotplug glitch), not just return an empty list.
  2. A stdlib ctypes Win32 ``EnumDisplayMonitors`` enumeration on Windows —
     so multi-monitor still works when ``screeninfo`` is absent.
  3. A single 1920x1080 monitor — so the feature never crashes detection.

This makes ``screeninfo`` optional: its absence only disables the
``screeninfo`` path; the ctypes fallback still gives real multi-monitor on
Windows, and the single-monitor fallback keeps single-window tiling alive
everywhere.
"""
from __future__ import annotations

import ctypes
import logging
import os
from typing import Any, Optional, TypedDict

logger = logging.getLogger(__name__)


class Monitor(TypedDict):
    """One physical display, in virtual-desktop pixel coordinates."""

    index: int
    x: int
    y: int
    width: int
    height: int
    name: str
    is_primary: bool


def _from_screeninfo() -> list[dict[str, Any]]:
    """Probe via the optional ``screeninfo`` package.

    Lazy import: ``screeninfo`` is not a hard dependency, and
    ``get_monitors()`` can RAISE on headless / RDP / hotplug sessions —
    both are swallowed so the caller falls through to the next probe.
    """
    try:
        from screeninfo import get_monitors  # type: ignore[import-untyped]
    except Exception:  # noqa: BLE001 — package absent or import-time failure
        return []
    try:
        raw = list(get_monitors())
    except Exception:  # noqa: BLE001 — ScreenInfoError, hotplug, no display
        logger.debug("screeninfo.get_monitors() raised; trying fallback", exc_info=True)
        return []
    mons: list[dict[str, Any]] = []
    for m in raw:
        try:
            mons.append(
                {
                    "x": int(m.x),
                    "y": int(m.y),
                    "width": int(m.width),
                    "height": int(m.height),
                    "name": (getattr(m, "name", None) or ""),
                    "is_primary": bool(getattr(m, "is_primary", False)),
                }
            )
        except Exception:  # noqa: BLE001 — a malformed entry; skip just it
            pass
    return mons


# DPI_AWARENESS_CONTEXT sentinels (passed to SetThreadDpiAwarenessContext as
# opaque pseudo-handles). PER_MONITOR_AWARE_V2 needs Win10 1703+; PER_MONITOR
# AWARE is the 1607 fallback. See the _from_win32 docstring for why we only set
# this for the THREAD, never the process.
_DPI_CONTEXT_PER_MONITOR_AWARE_V2 = -4
_DPI_CONTEXT_PER_MONITOR_AWARE = -3


class _ThreadDpiAware:
    """Make ONLY the current thread per-monitor-DPI-aware for the duration of a
    ``with`` block, restoring the previous context on exit.

    This is the tightly-scoped fix for mixed-DPI monitor probing: a DPI-unaware
    thread gets EnumDisplayMonitors/GetMonitorInfoW rectangles VIRTUALIZED to
    the primary monitor's DPI, so a secondary screen at a different scale is
    reported in the wrong coordinate space and ffplay is mis-placed/-sized.
    Setting the awareness on the THREAD (``SetThreadDpiAwarenessContext``, not
    the process) yields true physical rectangles for the enumeration WITHOUT
    changing process-wide awareness — so it never alters Tk's rendering or any
    other thread. Restored in ``__exit__`` so the thread is left exactly as
    found. A best-effort no-op when the API is missing (pre-1607) or fails.
    """

    def __init__(self) -> None:
        self._prev: Any = None
        self._fn: Any = None

    def __enter__(self) -> "_ThreadDpiAware":
        if os.name != "nt":
            return self
        try:
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            fn = getattr(user32, "SetThreadDpiAwarenessContext", None)
            if fn is None:  # Windows < 10 1607
                return self
            fn.restype = ctypes.c_void_p
            fn.argtypes = [ctypes.c_void_p]
            for ctx in (
                _DPI_CONTEXT_PER_MONITOR_AWARE_V2,
                _DPI_CONTEXT_PER_MONITOR_AWARE,
            ):
                prev = fn(ctypes.c_void_p(ctx))
                if prev:  # non-NULL => the context was accepted
                    self._fn = fn
                    self._prev = prev
                    break
        except Exception:  # noqa: BLE001 — never let DPI tuning break detection
            logger.debug("SetThreadDpiAwarenessContext unavailable", exc_info=True)
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._fn is not None and self._prev is not None:
            try:
                self._fn(ctypes.c_void_p(self._prev))
            except Exception:  # noqa: BLE001
                logger.debug("restoring thread DPI context failed", exc_info=True)


def _from_win32() -> list[dict[str, Any]]:
    """Enumerate monitors via the Win32 API using only the stdlib (ctypes).

    Fallback for when ``screeninfo`` is not installed. Uses
    ``EnumDisplayMonitors`` + ``GetMonitorInfoW``; the primary monitor is
    the one whose flags carry ``MONITORINFOF_PRIMARY`` (1). No-op (returns
    ``[]``) off Windows or on any ctypes/API failure.

    The enumeration runs inside :class:`_ThreadDpiAware` so the rectangles are
    true physical pixels even on a mixed-DPI multi-monitor desktop (a 150%
    laptop panel + a 100% external). The awareness is scoped to THIS thread for
    the call only and restored afterward — it never changes process-wide DPI
    awareness, so Tk rendering elsewhere is untouched.
    """
    if os.name != "nt":
        return []

    user32 = getattr(ctypes, "windll", None)
    if user32 is None:  # not Windows / no windll
        return []

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", _RECT),
            ("rcWork", _RECT),
            ("dwFlags", ctypes.c_ulong),
        ]

    mons: list[dict[str, Any]] = []
    # MonitorEnumProc: BOOL CALLBACK(HMONITOR, HDC, LPRECT, LPARAM). LPARAM is a
    # pointer-sized integer; c_void_p matches its width on both 32/64-bit so
    # the stack stays aligned and the callback isn't called with a corrupt
    # frame. We ignore HDC / LPRECT / LPARAM and read GetMonitorInfoW instead.
    monitor_enum_proc = ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(_RECT),
        ctypes.c_void_p,
    )

    def _callback(hmonitor: int, _hdc: Any, _lprect: Any, _lparam: Any) -> int:
        try:
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(_MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(  # type: ignore[attr-defined]
                ctypes.c_void_p(hmonitor), ctypes.byref(info)
            ):
                r = info.rcMonitor
                mons.append(
                    {
                        "x": int(r.left),
                        "y": int(r.top),
                        "width": int(r.right - r.left),
                        "height": int(r.bottom - r.top),
                        "name": "",
                        "is_primary": bool(info.dwFlags & 0x1),  # MONITORINFOF_PRIMARY
                    }
                )
        except Exception:  # noqa: BLE001 — never abort the enumeration
            logger.debug("GetMonitorInfoW failed for one monitor", exc_info=True)
        return 1  # keep enumerating

    try:
        # Per-monitor DPI awareness for THIS thread only (restored on exit), so
        # secondary screens at a different scale report true physical rects.
        with _ThreadDpiAware():
            ctypes.windll.user32.EnumDisplayMonitors(  # type: ignore[attr-defined]
                None, None, monitor_enum_proc(_callback), 0
            )
    except Exception:  # noqa: BLE001 — API unavailable / failed
        logger.debug("EnumDisplayMonitors failed", exc_info=True)
        return []
    return mons


def _single_fallback() -> list[dict[str, Any]]:
    """Last-resort single 1920x1080 monitor so detection never crashes."""
    return [
        {"x": 0, "y": 0, "width": 1920, "height": 1080, "name": "", "is_primary": True}
    ]


def list_monitors() -> list[Monitor]:
    """Return all monitors as plain dicts, ordered left-to-right, top-to-bottom.

    ``index`` is assigned AFTER the sort, so it is the spatial position
    (0 = top-left-most), which is far more stable across reboots / driver
    updates / hotplug than the OS enumeration order would be — a saved monitor
    selection then keeps pointing at the same physical screen.

    The sort key is the FULL tuple ``(x, y, name)`` — not x alone — so the order
    is total and deterministic even for monitors that share an x coordinate
    (vertically stacked / column-aligned displays). Sorting by x only would
    leave equal-x monitors in OS enumeration order, which is NOT stable across
    reboots / hotplug, so two stacked screens could swap indices between
    sessions and silently send playback to the wrong physical screen.

    Tries :func:`_from_screeninfo`, then :func:`_from_win32`, then a single
    1920x1080 fallback so the app/playback worker never crashes on detection.
    """
    raw = _from_screeninfo() or _from_win32() or _single_fallback()
    raw.sort(key=lambda mm: (mm["x"], mm["y"], mm.get("name") or ""))
    out: list[Monitor] = []
    for i, m in enumerate(raw):
        name = m.get("name") or "Display {}".format(i + 1)
        out.append(
            Monitor(
                index=i,
                x=int(m["x"]),
                y=int(m["y"]),
                width=int(m["width"]),
                height=int(m["height"]),
                name=name,
                is_primary=bool(m.get("is_primary", False)),
            )
        )
    if not out:  # defensive: every probe returned empty
        out.append(
            Monitor(
                index=0, x=0, y=0, width=1920, height=1080,
                name="Display 1", is_primary=True,
            )
        )
    return out


def primary_index(monitors: list[Monitor]) -> int:
    """Index of the primary monitor (falls back to the left-most one).

    Returns 0 for an empty list rather than raising IndexError, so a direct
    caller that somehow passes no monitors degrades gracefully. (The normal
    path feeds :func:`list_monitors` output, which is guaranteed non-empty.)
    """
    for m in monitors:
        if m["is_primary"]:
            return m["index"]
    return monitors[0]["index"] if monitors else 0


def select_monitors(
    monitors: list[Monitor],
    selected_indices: Optional[list[int]],
    multi_monitor: bool,
) -> list[Monitor]:
    """Decide which monitors actually get a player window.

    - ``multi_monitor`` off → a single monitor (the primary, or the first
      ticked one if a selection exists).
    - ``multi_monitor`` on  → every ticked monitor (or all monitors if none
      ticked).
    """
    if not monitors:
        # Defensive: with no monitors there is nothing to pick. The normal
        # path feeds list_monitors() output (guaranteed non-empty); this only
        # guards a direct caller that passes an empty list, where the primary
        # pick below would otherwise IndexError/KeyError.
        return []
    selected = list(selected_indices or [])
    by_index = {m["index"]: m for m in monitors}
    if not multi_monitor:
        for idx in selected:
            if idx in by_index:
                return [by_index[idx]]
        return [by_index[primary_index(monitors)]]
    chosen = [by_index[idx] for idx in selected if idx in by_index]
    return chosen or list(monitors)


def tile_filter_for(
    width: int, height: int, divisions: int
) -> tuple[str, int, int]:
    """Build the identical-tiles ffplay ``-vf`` for one monitor of the size.

    Uses the light ``fps*N^2`` method: duplicate each frame N² times then tile
    NxN so every cell shows the same frame. Returns
    ``(filter_string, out_width, out_height)``. Tile size is floored to even
    numbers (codec/scaler friendly); the output is the largest exact NxN
    multiple that fits the monitor.
    """
    n = max(1, int(divisions))
    tw = max(2, int(width) // n)
    th = max(2, int(height) // n)
    tw -= tw % 2
    th -= th % 2
    vf = (
        "scale=w={tw}:h={th}:flags=neighbor,"
        "fps=source_fps*{m},tile={n}x{n}"
    ).format(tw=tw, th=th, m=n * n, n=n)
    return vf, tw * n, th * n


def window_opts_for(
    monitor: Monitor, out_w: int, out_h: int, always_on_top: bool = True
) -> list[str]:
    """ffplay options to place a borderless window exactly over one monitor."""
    opts = ["-noborder"]
    if always_on_top:
        opts.append("-alwaysontop")
    opts += [
        "-left", str(monitor["x"]),
        "-top", str(monitor["y"]),
        "-x", str(int(out_w)),
        "-y", str(int(out_h)),
    ]
    return opts


def describe(monitor: Monitor) -> str:
    """Human-readable one-line label for a monitor (for the chooser dialog)."""
    tag = " [primary]" if monitor["is_primary"] else ""
    return "Monitor {n}: {w}x{h} @ ({x},{y}){tag}".format(
        n=monitor["index"] + 1,
        w=monitor["width"],
        h=monitor["height"],
        x=monitor["x"],
        y=monitor["y"],
        tag=tag,
    )
