"""Shared helpers for shaping user-facing error strings + retries.

Two helpers, both additive — adopt at call sites as you touch them
(audit B7 + B9). The point is uniform error reporting:

  * ``fmt_err(action, exc)`` — produces
    ``"<action> failed: <ExceptionType>: <message>"``
    Use whenever you propagate an exception into a user-visible
    string (log, messagebox, status bar). The exception class name
    is the support-engineer's first clue; the message is the
    user's.

  * ``with_retries(fn, attempts, backoff)`` — runs ``fn`` until it
    succeeds or runs out of attempts. Logs each retry. Returns
    whatever ``fn`` returns; re-raises the last exception on
    exhaustion.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def fmt_err(action: str, exc: BaseException | object) -> str:
    """Format an exception into a user-friendly string.

    Examples
    --------
    >>> fmt_err("Model download", FileNotFoundError("model.bin missing"))
    'Model download failed: FileNotFoundError: model.bin missing'

    Used in two contexts:
      * UI log lines (``app.log(fmt_err("Diarisation", e))``)
      * Stored error fields (``task.error = fmt_err("Transcription", e)``)

    Defensive about non-Exception inputs because legacy call sites
    sometimes pass already-stringified error messages through and we
    don't want a fresh exception inside the error-formatting helper.
    """
    if not isinstance(exc, BaseException):
        return f"{action} failed: {exc}"
    name = type(exc).__name__
    message = str(exc) or "(no message)"
    return f"{action} failed: {name}: {message}"


def with_retries(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
    backoff_multiplier: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    label: str = "",
) -> T:
    """Run ``fn`` until it succeeds or runs out of ``attempts``.

    Each failure is logged at WARNING with the attempt number; the
    final failure re-raises so the caller can decide what to do.
    Exponential backoff between attempts.

    Parameters
    ----------
    fn:
        Zero-arg callable. Use ``functools.partial`` or a lambda
        to bind arguments.
    attempts:
        Total tries including the first (so ``attempts=1`` means
        no retries).
    backoff_seconds:
        Sleep before the second attempt; multiplied by
        ``backoff_multiplier`` after each subsequent failure.
    retry_on:
        Tuple of exception types to retry on. Other types abort
        immediately. Defaults to broad ``Exception`` because the
        helper itself doesn't know what's worth retrying.
    label:
        Free-form name used in the retry log line. Defaults to the
        callable's ``__name__``.
    """
    pretty = label or getattr(fn, "__name__", "operation")
    if attempts < 1:
        raise ValueError(f"attempts must be ≥ 1, got {attempts}")
    delay = max(0.0, float(backoff_seconds))
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except retry_on as e:
            last_exc = e
            if attempt >= attempts:
                logger.warning(
                    "%s exhausted retries after %d attempts: %s: %s",
                    pretty, attempts, type(e).__name__, e,
                )
                raise
            logger.warning(
                "%s attempt %d/%d failed (%s: %s); retrying in %.1fs",
                pretty, attempt, attempts, type(e).__name__, e, delay,
            )
            if delay > 0:
                time.sleep(delay)
            delay *= max(1.0, float(backoff_multiplier))
    # unreachable — kept for type checkers
    assert last_exc is not None  # noqa: S101
    raise last_exc
