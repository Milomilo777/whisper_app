"""Optional Sentry crash reporting.

Activated only if the ``SENTRY_DSN`` environment variable is set. No DSN ever
ships in code or config. Quietly does nothing when the env var is empty or
when ``sentry-sdk`` is not installed.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def init_sentry() -> bool:
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk  # type: ignore[import-not-found]
    except ImportError:
        logger.info("SENTRY_DSN set but sentry-sdk is not installed; skipping")
        return False
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0, send_default_pii=False)
    logger.info("Sentry crash reporting enabled")
    return True
