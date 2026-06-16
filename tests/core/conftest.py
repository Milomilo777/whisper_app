"""Shared pytest fixtures for the core test suite.

Autouse isolation guard: several tests call the REAL transcriber load
functions (``load_existing_model``, ``_load_whisper_model_self_healing``,
``_load_alt_backend``), which mutate ``core.transcriber`` module globals via
``global`` statements. ``monkeypatch`` cannot undo those (it only reverts
attributes it set itself), so without this guard a test that activates a fake
model or an alternate backend leaks that state into later test files — which
produces order-dependent failures whose set shifts with machine state (for
example whether a bundled Google Cloud key flips the default engine to cloud
STT). See ``docs/TEST_ISOLATION_FOLLOWUP.md``.

This snapshots + restores (NOT resets) the globals around every test, so a
module-scoped model fixture (e.g. ``test_v08_real_file_e2e``) is preserved
within its own module while cross-file leakage is contained at the source.
"""
from __future__ import annotations

import pytest

# core.transcriber module globals that the real load paths mutate in place.
_TRANSCRIBER_GLOBALS = (
    "MODEL",
    "PIPELINE",
    "MODEL_READY",
    "MODEL_ERROR",
    "_ALT_BACKEND",
    "_ALT_BACKEND_NAME",
)


@pytest.fixture(autouse=True)
def _isolate_transcriber_globals():
    """Snapshot core.transcriber module globals; restore them after the test."""
    try:
        import core.transcriber as _t
    except Exception:  # noqa: BLE001 — an import failure here is unrelated
        yield
        return
    sentinel = object()
    saved = {name: getattr(_t, name, sentinel) for name in _TRANSCRIBER_GLOBALS}
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is not sentinel:
                setattr(_t, name, value)


@pytest.fixture(autouse=True)
def _default_offline_backend(monkeypatch):
    """Pin core.transcriber's active backend to faster_whisper for tests.

    ``core.transcriber.config`` is loaded once at import; on a dev/build
    machine that ships ``creds/gcloud_stt.json`` the resolved default becomes
    ``google_cloud_stt``, which silently routes tests that mock the offline
    ``MODEL`` through the cloud path and breaks them. Forcing the offline
    backend here makes the suite deterministic regardless of whether a bundled
    key is present (mirrors CI). ``setitem`` is auto-reverted, and a test that
    explicitly exercises a cloud backend (by reassigning ``config``) still
    wins.
    """
    try:
        import core.transcriber as _t
    except Exception:  # noqa: BLE001
        return
    if isinstance(getattr(_t, "config", None), dict):
        monkeypatch.setitem(_t.config, "transcribe_backend", "faster_whisper")
