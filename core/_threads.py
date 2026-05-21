"""Safer ``threading.Thread`` wrappers.

A raw ``threading.Thread`` that raises in its target function simply
dies — no stack trace, no log, nothing in the UI. The thread object's
``is_alive()`` flips to False and the caller can't tell whether the
work completed or crashed.

Across this codebase there are ~10 ``threading.Thread(target=…).start()``
call sites (audit B3). Migrating them in one big sweep risks subtle
regressions because each call site has slightly different error-
handling expectations. Instead we ship :func:`safe_thread` here as
an additive helper. New code adopts it from day 1; old code is
migrated piece-by-piece in later batches (roadmap FB-03).

Usage::

    from core._threads import safe_thread

    safe_thread(my_worker, args=(x, y), name="my-worker")

Equivalent today to::

    threading.Thread(target=my_worker, args=(x, y),
                     name="my-worker", daemon=True).start()

…except that an uncaught exception inside ``my_worker`` is logged
via ``logger.exception`` with the thread name in the message,
instead of vanishing silently.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Iterable, Mapping

logger = logging.getLogger(__name__)


def safe_thread(
    target: Callable[..., Any],
    *,
    args: Iterable[Any] = (),
    kwargs: Mapping[str, Any] | None = None,
    name: str | None = None,
    daemon: bool = True,
    start: bool = True,
) -> threading.Thread:
    """Spawn a daemon thread whose uncaught exceptions are logged.

    Parameters
    ----------
    target:
        The callable to run in the thread.
    args, kwargs:
        Positional / keyword arguments forwarded to ``target``.
    name:
        Optional thread name. Used in the failure log message so the
        operator can tell which subsystem crashed. Defaults to
        ``target.__name__`` if not supplied.
    daemon:
        Whether to mark the thread as daemonic. Defaults to ``True``
        because virtually every background thread in this codebase
        should die with the process.
    start:
        Whether to call ``.start()`` before returning. Set to
        ``False`` only when the caller needs to attach extra state
        to the Thread object before launching.

    Returns
    -------
    threading.Thread
        The freshly-spawned (and, by default, already-running) thread.
        The caller typically discards this.

    Failure mode
    ------------
    If ``target`` raises, the exception is caught and logged via
    ``logger.exception(...)``. The thread then exits normally — i.e.
    the caller can NOT detect the failure from the returned Thread
    object. This is intentional: we treat thread death as observable
    via logs (the universal contract), not via thread state.
    """
    kwargs_dict = dict(kwargs) if kwargs is not None else {}
    pretty_name = name or getattr(target, "__name__", "anonymous")

    def _runner() -> None:
        try:
            target(*args, **kwargs_dict)
        except Exception:  # noqa: BLE001 — top of a worker thread,
            #   no caller exists to receive the exception.
            logger.exception(
                "Background thread %r crashed; swallowing to keep the "
                "process alive. Investigate above stack trace.",
                pretty_name,
            )

    thread = threading.Thread(
        target=_runner,
        name=pretty_name,
        daemon=daemon,
    )
    if start:
        thread.start()
    return thread
