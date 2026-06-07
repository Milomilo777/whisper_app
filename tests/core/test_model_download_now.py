"""Regression tests for the Advanced "Download now" path (HIGH-3).

App.download_model_now must NOT short-circuit on the app-global
``model_ready`` flag. ``ensure_model_with_modal`` early-returns True when any
model is loaded, so once a model was loaded the Advanced "Download now"
button silently did nothing. ``download_model_now`` opens the modal
regardless of ``model_ready`` (``ensure_model`` is idempotent — a fast MD5
check when the bytes are already present).

Runs against SimpleNamespace fakes — no real Tk root (project rule).
"""
from __future__ import annotations

import types


def test_download_model_now_opens_modal_even_when_model_ready() -> None:
    from app import app as app_module

    opened = {"count": 0}

    def _fake_open(mandatory=False):  # bound to the fake instance below
        opened["count"] += 1
        return True

    fake = types.SimpleNamespace(
        model_ready=True,
        _open_model_download_modal=_fake_open,
    )
    result = app_module.App.download_model_now(fake)  # type: ignore[arg-type]

    assert result is True
    assert opened["count"] == 1, (
        "download_model_now must open the modal even when model_ready is True"
    )


def test_ensure_model_with_modal_still_short_circuits_when_ready() -> None:
    """The general ensure path keeps its model_ready fast-return (unchanged)."""
    from app import app as app_module

    opened = {"count": 0}

    def _fake_open(mandatory=False):
        opened["count"] += 1
        return True

    fake = types.SimpleNamespace(
        model_ready=True,
        status_var=types.SimpleNamespace(set=lambda _v: None),
        _open_model_download_modal=_fake_open,
    )
    assert app_module.App.ensure_model_with_modal(fake) is True  # type: ignore[arg-type]
    assert opened["count"] == 0  # short-circuited, modal never opened
