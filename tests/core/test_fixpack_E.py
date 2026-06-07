"""Fixpack E regression tests — core/tiling.py + core/monitors.py.

Hermetic: NO real Tk root, NO network, NO real ffplay/yt-dlp/pip, NO real
display. The tiling tests stub the process lifecycle (``_start`` / ``_terminate``)
and the self-heal so the worker run-loop and its run-token / responsiveness
guards can be exercised in-process; the monitor tests stub the probes.

Covers four confirmed findings:
  1. start()+stop() reviving the OLD worker so two reconnect loops race over
     shared state -> a monotonic run-token (generation) makes a superseded
     worker exit and never touch shared state or the status line.
  2. Stop ignored for up to ~8 min while a synchronous yt-dlp/pip self-heal
     runs -> the in-loop self-heal runs off-thread with an interruptible,
     token-gated wait, and is skipped when a stop is already pending.
  3. list_monitors() unstable for monitors that share an x coordinate
     (vertically stacked) -> the sort key is the full (x, y, name) tuple.
  4. Mixed-DPI rectangles -> a THREAD-scoped (never process-wide) DPI-aware
     context wraps the Win32 enumeration and is a safe no-op off Windows.
"""
from __future__ import annotations

import sys
import threading
import time
import types

from core import monitors, tiling


# ===========================================================================
# Finding 1 — run-token guard: a superseded worker must not revive / clobber
# ===========================================================================
def test_start_bumps_generation_and_invalidates_old_run():
    """A fresh start() supersedes the prior run's token, so the old worker's
    activity guard goes False even while _play_flag is True for the new run."""
    c = tiling.TilingController()
    # Simulate the controller mid-run on generation G with the flag set.
    c._play_flag = True
    c._generation = 7
    old_gen = c._generation
    assert c._is_active(old_gen) is True

    # A new run bumps the token; _play_flag is True again for the NEW run.
    c._generation += 1
    c._play_flag = True
    # The OLD worker, re-checking with its captured token, is now inactive...
    assert c._is_active(old_gen) is False
    # ...while the NEW run's token is active.
    assert c._is_active(c._generation) is True


def test_superseded_worker_run_exits_without_starting_or_clobbering():
    """Drive the run-loop for a STALE generation: it must not call _start, must
    not run _terminate (which would null a live run's published handles), and
    must not overwrite the live run's status line with 'Stopped.'.
    """
    c = tiling.TilingController()
    started: list[int] = []
    terminated: list[bool] = []
    statuses: list[str] = []

    c._start = lambda my_gen: started.append(my_gen)  # type: ignore[assignment]
    c._terminate = lambda join=True: terminated.append(join)  # type: ignore[assignment]
    c._status = lambda msg, color: statuses.append(msg)  # type: ignore[assignment]

    # The live run is generation 5; the stale worker was launched on 4.
    c._generation = 5
    c._play_flag = True
    c._run(my_gen=4)

    assert started == []           # never (re)started the pipeline
    assert terminated == []        # never tore down the live run's state
    assert "Stopped." not in statuses  # never clobbered the live status line


def test_owning_worker_run_does_terminate_and_reports_stopped():
    """The complementary case: a normally-stopped worker (token unchanged) DOES
    tear down and DOES report 'Stopped.' — the fix must not regress that.
    """
    c = tiling.TilingController()
    terminated: list[bool] = []
    statuses: list[str] = []
    c._start = lambda my_gen: None  # type: ignore[assignment]
    c._terminate = lambda join=True: terminated.append(join)  # type: ignore[assignment]
    c._status = lambda msg, color: statuses.append(msg)  # type: ignore[assignment]

    c._generation = 9
    c._play_flag = False  # a Stop was requested; generation is unchanged
    c._run(my_gen=9)

    assert terminated, "the owning worker must run its terminal teardown"
    assert statuses and statuses[-1] == "Stopped."


# ===========================================================================
# Finding 2 — Stop stays responsive during a blocking self-heal
# ===========================================================================
def test_run_self_heal_returns_promptly_when_stop_requested(monkeypatch):
    """The in-loop self-heal blocks for up to ~8 min in yt-dlp -U/pip. The
    worker must observe a Stop (flag cleared) WITHOUT waiting for that to
    finish. We make the heal block on an event and assert _run_self_heal
    returns quickly after the stop, well before the heal is released.
    """
    c = tiling.TilingController()
    c._generation = 1
    c._play_flag = True

    heal_running = threading.Event()
    release_heal = threading.Event()

    def blocking_heal(_log):
        heal_running.set()
        # Stand in for subprocess.run([... 'yt-dlp', '-U'], timeout=180): block.
        release_heal.wait(timeout=10)

    monkeypatch.setattr(c, "_self_heal_ytdlp", blocking_heal)

    def caller():
        c._run_self_heal(my_gen=1)

    t = threading.Thread(target=caller, daemon=True)
    t.start()
    assert heal_running.wait(timeout=2), "self-heal thread never launched"

    # Operator hits Stop: clear the flag (exactly what stop() does).
    c._play_flag = False
    started = time.monotonic()
    t.join(timeout=3)
    elapsed = time.monotonic() - started

    assert not t.is_alive(), "the worker did not become responsive to Stop"
    # It returned because of the flag, NOT because the heal finished.
    assert not release_heal.is_set()
    assert elapsed < 2.0
    # Let the still-blocked heal thread unwind cleanly.
    release_heal.set()


def test_run_self_heal_returns_when_superseded_by_new_run(monkeypatch):
    """A new run (bumped generation) must also free the worker from the heal
    wait, even though _play_flag stays True for the new run."""
    c = tiling.TilingController()
    c._generation = 3
    c._play_flag = True

    heal_running = threading.Event()
    release_heal = threading.Event()

    def blocking_heal(_log):
        heal_running.set()
        release_heal.wait(timeout=10)

    monkeypatch.setattr(c, "_self_heal_ytdlp", blocking_heal)

    t = threading.Thread(target=lambda: c._run_self_heal(my_gen=3), daemon=True)
    t.start()
    assert heal_running.wait(timeout=2)

    # A new start() superseded this worker; flag stays True for the new run.
    c._generation = 4
    t.join(timeout=3)
    assert not t.is_alive()
    assert not release_heal.is_set()
    release_heal.set()


def test_inloop_self_heal_uses_offthread_runner_not_blocking_call(monkeypatch):
    """The in-loop self-heal must dispatch through _run_self_heal (off-thread +
    interruptible), NOT call the blocking _self_heal_ytdlp synchronously on the
    worker — that synchronous call is what froze Stop for up to ~8 minutes.

    We drive ONE iteration where a session drops while the worker is still
    active, stub _wait_backoff to immediately request a stop so the loop ends,
    and assert the heal went via the off-thread runner.
    """
    c = tiling.TilingController()
    via_runner: list[int] = []
    via_blocking: list[int] = []

    c._start = lambda my_gen: None  # type: ignore[assignment]
    c._terminate = lambda join=True: None  # type: ignore[assignment]
    c._status = lambda *a: None  # type: ignore[assignment]
    c._log = lambda *a: None  # type: ignore[assignment]
    c._alive = lambda: False  # type: ignore[assignment]  # session drops at once

    monkeypatch.setattr(c, "_run_self_heal", lambda my_gen: via_runner.append(my_gen))
    monkeypatch.setattr(c, "_self_heal_ytdlp", lambda log: via_blocking.append(1))

    # After the heal gate, end the loop by clearing the flag in the backoff.
    def _stop_after_backoff(backoff, my_gen):
        c._play_flag = False

    monkeypatch.setattr(c, "_wait_backoff", _stop_after_backoff)

    c._auto_restart = True
    c._generation = 1
    c._play_flag = True
    c._fail_count = tiling.TilingController.HEAL_AFTER_FAILS - 1  # +1 in-loop hits the gate
    c._healed = False

    c._run(my_gen=1)
    assert via_runner == [1], "in-loop heal must dispatch through _run_self_heal"
    assert via_blocking == [], "must NOT call the blocking heal synchronously"


# ===========================================================================
# Finding 3 — stable spatial order for monitors sharing an x coordinate
# ===========================================================================
class _M:
    def __init__(self, x, y, w, h, name="", primary=False):
        self.x, self.y, self.width, self.height = x, y, w, h
        self.name, self.is_primary = name, primary


def _fake_screeninfo(raw):
    mod = types.ModuleType("screeninfo")
    mod.get_monitors = lambda: raw  # type: ignore[attr-defined]
    return mod


def test_stacked_monitors_sharing_x_keep_stable_top_to_bottom_order(monkeypatch):
    """Two equal-x (vertically stacked) monitors must index top-to-bottom by y,
    regardless of the OS enumeration order — so a saved selection keeps
    pointing at the same physical screen across reboots / hotplug.
    """
    # Same x=0; top screen at y=0, bottom at y=1080. Feed them BOTTOM-first to
    # mimic an OS enumeration that lists the lower screen first.
    raw_bottom_first = [
        _M(0, 1080, 1920, 1080, "BOTTOM"),
        _M(0, 0, 1920, 1080, "TOP"),
    ]
    monkeypatch.setitem(sys.modules, "screeninfo", _fake_screeninfo(raw_bottom_first))
    mons = monitors.list_monitors()
    assert [m["y"] for m in mons] == [0, 1080]
    assert [m["name"] for m in mons] == ["TOP", "BOTTOM"]
    assert [m["index"] for m in mons] == [0, 1]

    # The SAME physical layout enumerated TOP-first must yield the SAME indices.
    raw_top_first = [
        _M(0, 0, 1920, 1080, "TOP"),
        _M(0, 1080, 1920, 1080, "BOTTOM"),
    ]
    monkeypatch.setitem(sys.modules, "screeninfo", _fake_screeninfo(raw_top_first))
    mons2 = monitors.list_monitors()
    assert [(m["name"], m["index"]) for m in mons2] == [("TOP", 0), ("BOTTOM", 1)]


def test_left_to_right_still_wins_over_y(monkeypatch):
    """x remains the primary key: a right-but-higher screen still indexes after
    a left-but-lower one (no regression to the documented left-to-right order).
    """
    raw = [
        _M(1920, 0, 1920, 1080, "RIGHT_TOP"),
        _M(0, 1080, 1920, 1080, "LEFT_BOTTOM"),
    ]
    monkeypatch.setitem(sys.modules, "screeninfo", _fake_screeninfo(raw))
    mons = monitors.list_monitors()
    assert [m["name"] for m in mons] == ["LEFT_BOTTOM", "RIGHT_TOP"]
    assert [m["x"] for m in mons] == [0, 1920]


def test_equal_x_and_y_break_tie_on_name_deterministically(monkeypatch):
    """Degenerate identical (x, y): the name tie-break keeps the order total and
    independent of enumeration order."""
    raw_a = [_M(0, 0, 800, 600, "Z"), _M(0, 0, 800, 600, "A")]
    monkeypatch.setitem(sys.modules, "screeninfo", _fake_screeninfo(raw_a))
    names_a = [m["name"] for m in monitors.list_monitors()]
    raw_b = [_M(0, 0, 800, 600, "A"), _M(0, 0, 800, 600, "Z")]
    monkeypatch.setitem(sys.modules, "screeninfo", _fake_screeninfo(raw_b))
    names_b = [m["name"] for m in monitors.list_monitors()]
    assert names_a == names_b == ["A", "Z"]


# ===========================================================================
# Finding 4 — thread-scoped (not process-wide) DPI awareness for the Win32 probe
# ===========================================================================
def test_thread_dpi_aware_is_safe_context_manager():
    """_ThreadDpiAware must be a no-raise context manager everywhere (a no-op
    off Windows / when the API is missing) — it must never break detection."""
    with monitors._ThreadDpiAware() as guard:
        assert guard is not None
    # Re-entrant / repeated use is harmless.
    with monitors._ThreadDpiAware():
        pass


def test_thread_dpi_aware_restores_previous_context(monkeypatch):
    """When the SetThreadDpiAwarenessContext API IS present, the guard sets a
    per-monitor context on ENTER and RESTORES the previous one on EXIT — i.e.
    it is thread-scoped and reversible, never a process-wide change.
    """
    calls: list = []

    class _FakeFn:
        restype = None
        argtypes = None

        def __call__(self, ctx):
            calls.append(getattr(ctx, "value", ctx))
            # Return a non-NULL "previous context" so the guard records it.
            return 999

    fake_user32 = types.SimpleNamespace(
        SetThreadDpiAwarenessContext=_FakeFn()
    )
    fake_windll = types.SimpleNamespace(user32=fake_user32)
    monkeypatch.setattr(monitors.ctypes, "windll", fake_windll, raising=False)
    monkeypatch.setattr(monitors.os, "name", "nt")

    # c_void_p(-4) wraps to its unsigned 2's-complement value; compare against
    # the same wrap rather than the raw signed sentinel.
    want_v2 = monitors.ctypes.c_void_p(
        monitors._DPI_CONTEXT_PER_MONITOR_AWARE_V2
    ).value
    with monitors._ThreadDpiAware():
        # Entered: one call to set a per-monitor-aware context.
        assert len(calls) == 1
        assert calls[0] == want_v2
    # Exited: restored the previous (999) context => thread-scoped + reversible.
    assert calls[-1] == 999
    assert len(calls) == 2


def test_from_win32_noop_off_windows(monkeypatch):
    """Sanity: the Win32 probe (which now wraps EnumDisplayMonitors in the DPI
    guard) is still a clean no-op off Windows."""
    monkeypatch.setattr(monitors.os, "name", "posix")
    assert monitors._from_win32() == []
