"""Backlog fix-pack regressions for the Video Tiling engine + monitor helpers.

Hermetic: no tk.Tk(), no real display, no network, no real subprocess. Every
test drives a method directly with fakes.

Covers three backlog candidates:

  1. tiling: TilingController._alive() / _death_reason() read the shared
     pipeline fields (self._ytdlp, self._ffplay, ...) WITHOUT the lock while a
     UI-thread Stop runs _terminate concurrently. Reading self._ytdlp truthy
     and THEN calling .poll() on it could hit None.poll() once Stop nulled it.
     Fix: snapshot the fields under self._lock first.

  2. tiling: a killed yt-dlp / ffplay child is never wait()-ed, so on POSIX it
     lingers as a <defunct> zombie. The reconnect loop tears a pipeline down on
     every dropped session, so zombies pile up over a long outage. Fix:
     _terminate reaps (wait()s) every killed child.

  3. monitors: primary_index([]) / select_monitors([], ...) raised IndexError /
     KeyError on an empty monitor list. Fix: both degrade gracefully.
"""
from __future__ import annotations

import threading

from core import monitors, tiling


# --------------------------------------------------------------------------- #
#  Candidate 1 — _alive() / _death_reason() snapshot shared state under lock
# --------------------------------------------------------------------------- #
class _NullingProc:
    """A fake process that nulls ctrl._ytdlp the instant its truthiness is read.

    This reproduces the unlocked-read race deterministically. The pre-fix code
    was ``if not self._ytdlp or self._ytdlp.poll() is not None:`` — two SEPARATE
    reads of self._ytdlp. A concurrent _terminate (UI-thread Stop) nulls the
    field between them: the truthiness read sees the proc, then the second read
    sees None and ``None.poll()`` raises AttributeError. Nulling on __bool__
    pins that exact interleaving without real threads. The snapshot fix takes
    ONE consistent read under the lock, so the local reference survives.
    """

    def __init__(self, ctrl):
        self._ctrl = ctrl

    def __bool__(self):
        # Simulate a concurrent Stop nulling the live download the moment the
        # field's truthiness is evaluated (the first of two unlocked reads).
        self._ctrl._ytdlp = None
        return True

    def poll(self):
        return None  # still "alive" if anyone holds a real reference


def test_alive_snapshots_ytdlp_under_lock_no_crash():
    ctrl = tiling.TilingController()
    proc = _NullingProc(ctrl)
    ctrl._ytdlp = proc  # type: ignore[assignment]
    ctrl._ffplay = []
    ctrl._consumers = []
    # Pre-fix this raised AttributeError (None.poll()); post-fix the snapshot
    # holds a local ref, so the field nulling is harmless and it just returns.
    assert ctrl._alive() is False  # no ffplay windows -> not alive overall


def test_death_reason_snapshots_ytdlp_under_lock_no_crash():
    ctrl = tiling.TilingController()
    proc = _NullingProc(ctrl)
    ctrl._ytdlp = proc  # type: ignore[assignment]
    ctrl._ffplay = []
    ctrl._stderr_tail = None
    # Pre-fix this raised AttributeError on the nulled field; post-fix it does
    # not crash and returns a human reason string.
    reason = ctrl._death_reason()
    assert isinstance(reason, str) and reason


def test_alive_and_death_reason_acquire_the_lock():
    """The snapshot must be taken while holding self._lock."""
    ctrl = tiling.TilingController()
    acquired = {"n": 0}
    real_lock = ctrl._lock

    class _CountingLock:
        def __enter__(self):
            acquired["n"] += 1
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    ctrl._lock = _CountingLock()  # type: ignore[assignment]
    ctrl._ytdlp = None
    ctrl._ffplay = []
    ctrl._consumers = []
    ctrl._stderr_tail = None
    ctrl._alive()
    ctrl._death_reason()
    assert acquired["n"] >= 2  # each method snapshotted under the lock


def test_alive_reports_dead_when_a_player_exited():
    """Sanity: the alive logic itself is unchanged for the happy path."""
    class _P:
        def __init__(self, code):
            self._code = code

        def poll(self):
            return self._code

    ctrl = tiling.TilingController()
    ctrl._ytdlp = _P(None)  # type: ignore[assignment]
    ctrl._consumers = []
    ctrl._ffplay = [_P(None), _P(0)]  # type: ignore[list-item]
    assert ctrl._alive() is False  # one window exited


def test_alive_true_when_everything_running():
    class _P:
        def poll(self):
            return None

    ctrl = tiling.TilingController()
    ctrl._ytdlp = _P()  # type: ignore[assignment]
    ctrl._consumers = [{"dead": False}]
    ctrl._ffplay = [_P()]  # type: ignore[list-item]
    assert ctrl._alive() is True


# --------------------------------------------------------------------------- #
#  Candidate 2 — _terminate reaps killed children (no POSIX zombies)
# --------------------------------------------------------------------------- #
class _RecordingProc:
    """Fake Popen recording whether wait() (reaping) was called."""

    def __init__(self):
        self.pid = 4321
        self.stdin = None
        self.stdout = None
        self.waited = False
        self._killed = False

    def poll(self):
        # Report "still running" until killed, then exited — so
        # kill_process_tree's early-return-if-exited does not skip it, and a
        # later poll/wait sees it gone.
        return 0 if self._killed else None

    def wait(self, timeout=None):
        self.waited = True
        return 0

    def kill(self):
        self._killed = True

    def terminate(self):
        self._killed = True


def test_terminate_reaps_every_killed_child(monkeypatch):
    """Each yt-dlp / ffplay / consumer process must be wait()-ed on teardown so
    it does not linger as a POSIX zombie."""
    # Neutralise the real OS kill; just mark the fake as killed so poll() flips.
    def fake_kill(process, *, force=False, timeout=5.0):
        if process is not None:
            process.kill()

    monkeypatch.setattr(tiling, "kill_process_tree", fake_kill)

    ctrl = tiling.TilingController()
    ytdlp = _RecordingProc()
    ff = _RecordingProc()
    cons_proc = _RecordingProc()

    class _Q:
        def put_nowait(self, _v):
            pass

    ctrl._ytdlp = ytdlp  # type: ignore[assignment]
    ctrl._ffplay = [ff]  # type: ignore[list-item]
    ctrl._consumers = [{"proc": cons_proc, "q": _Q(), "thread": None, "dead": False}]
    ctrl._fanout_stop = None

    ctrl._terminate(join=False)

    assert ytdlp.waited, "yt-dlp was not reaped (zombie risk)"
    assert ff.waited, "ffplay was not reaped (zombie risk)"
    assert cons_proc.waited, "consumer ffplay was not reaped (zombie risk)"
    # Fields cleared as before.
    assert ctrl._ytdlp is None
    assert ctrl._ffplay == []
    assert ctrl._consumers == []


def test_reap_never_raises_on_timeout_or_none():
    class _Stuck:
        def wait(self, timeout=None):
            raise Exception("TimeoutExpired-like")  # noqa: TRY002

    # None entries skipped; a wait() that raises is swallowed.
    tiling.TilingController._reap([None, _Stuck()])  # type: ignore[list-item]


def test_terminate_runs_with_empty_pipeline():
    """A no-op teardown (nothing spawned yet) must not crash and reaps nothing."""
    ctrl = tiling.TilingController()
    ctrl._terminate(join=False)  # all fields are their empty defaults
    assert ctrl._ytdlp is None


# --------------------------------------------------------------------------- #
#  Candidate 3 — monitors empty-list guards
# --------------------------------------------------------------------------- #
def _mon(index, primary=False):
    return monitors.Monitor(
        index=index, x=index * 1920, y=0, width=1920, height=1080,
        name="Display {}".format(index + 1), is_primary=primary,
    )


def test_primary_index_empty_list_returns_zero_not_indexerror():
    assert monitors.primary_index([]) == 0


def test_primary_index_still_prefers_flagged_then_leftmost():
    assert monitors.primary_index([_mon(0), _mon(1, primary=True)]) == 1
    assert monitors.primary_index([_mon(0), _mon(1)]) == 0


def test_select_monitors_empty_list_returns_empty_not_keyerror():
    # Single-window path would otherwise do by_index[primary_index([])] -> KeyError.
    assert monitors.select_monitors([], None, multi_monitor=False) == []
    assert monitors.select_monitors([], [0], multi_monitor=False) == []
    assert monitors.select_monitors([], None, multi_monitor=True) == []


def test_select_monitors_nonempty_unchanged():
    mons = [_mon(0, primary=True), _mon(1)]
    # Single, no selection -> primary.
    assert monitors.select_monitors(mons, [], multi_monitor=False) == [mons[0]]
    # Multi, none ticked -> all.
    assert monitors.select_monitors(mons, [], multi_monitor=True) == mons
