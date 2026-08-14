"""Regression test for App._drain_watched_paths and one-bad-path stalls.

_enqueue_watched_file used to share a single try/except with the
get_nowait() loop, so ``queue.Empty`` (the intended stop signal) and any
real exception from _enqueue_watched_file were caught the same way --
one path that kept raising (e.g. a file the OS holds locked) ended that
tick's drain immediately, silently skipping every other path still
sitting in the queue behind it.

These tests run App._drain_watched_paths against a SimpleNamespace fake
"self" (no real Tk root, per the project's Tk-free-tests rule).
"""
from __future__ import annotations

import queue
import types
from typing import Any


def _fake_self(paths: list[str], enqueue: Any) -> types.SimpleNamespace:
    q: queue.Queue[str] = queue.Queue()
    for p in paths:
        q.put(p)
    return types.SimpleNamespace(
        _closing=False,
        _watched_path_queue=q,
        _enqueue_watched_file=enqueue,
        _drain_watched_paths=lambda: None,  # self.after's 2nd arg only
        after=lambda *_a, **_k: None,
    )


def test_one_raising_path_does_not_block_a_later_good_path() -> None:
    from app import app as app_module

    seen: list[str] = []

    def enqueue(path: str) -> None:
        if path == "bad.mp4":
            raise OSError("locked")
        seen.append(path)

    fake = _fake_self(["bad.mp4", "good.mp4"], enqueue)
    app_module.App._drain_watched_paths(fake)  # type: ignore[arg-type]

    assert seen == ["good.mp4"], (
        "a path that raises must not stop the same tick's drain from "
        "reaching paths queued behind it"
    )


def test_empty_queue_drains_cleanly_and_rearms() -> None:
    from app import app as app_module

    rearmed: list[Any] = []
    fake = _fake_self([], lambda _p: None)
    fake.after = lambda delay, fn: rearmed.append((delay, fn))

    app_module.App._drain_watched_paths(fake)  # type: ignore[arg-type]

    assert len(rearmed) == 1
    assert rearmed[0][0] == 250


def test_all_raising_paths_still_rearms() -> None:
    """Every path can fail and the periodic re-arm must still happen --
    otherwise the whole watched-folder feature dies silently after one
    bad tick (this is the failure mode _closing already guards for
    elsewhere; here we're confirming a raising item doesn't imitate it)."""
    from app import app as app_module

    def always_raises(_path: str) -> None:
        raise OSError("locked")

    rearmed: list[Any] = []
    fake = _fake_self(["a.mp4", "b.mp4"], always_raises)
    fake.after = lambda delay, fn: rearmed.append((delay, fn))

    app_module.App._drain_watched_paths(fake)  # type: ignore[arg-type]

    assert len(rearmed) == 1
