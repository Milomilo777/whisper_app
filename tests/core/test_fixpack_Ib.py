"""Fixpack Ib regression tests for app/dialogs/advanced.py.

Finding (cluster Ib): the Batch-size control is a free-text ttk.Spinbox
bound to a tk.IntVar (no readonly / no validatecommand). A user can clear
the field or type a stray character, then click Save. _save_and_close used
to read it with a bare ``int(self._batch_size.get())`` OUTSIDE any
try/except — and tk.IntVar.get() raises tkinter.TclError when the widget
holds non-integer text. The exception fired BEFORE save_config(), so the
Save aborted and NONE of the user's other Advanced-dialog edits were
persisted.

The fix reads the batch size defensively, falling back to the prior saved
value (then the default) so Save never crashes and never loses other edits.

Hermetic: SimpleNamespace fakes + stub Vars, no real Tk root / network /
model. Mirrors tests/core/test_advanced_model_change.py.
"""
from __future__ import annotations

import tkinter as tk
import types
from typing import Any

import pytest


class _V:
    """Minimal stand-in for a Tk *Var: .get() returns a fixed value."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def get(self) -> Any:
        return self._value


class _BadIntVar:
    """Stand-in for a tk.IntVar whose Spinbox holds non-integer text.

    A real tk.IntVar.get() raises tkinter.TclError ("expected integer but
    got ...") when the bound widget contains non-numeric / empty text. This
    reproduces that exact failure mode without a live Tcl interpreter.
    """

    def __init__(self, raw: str) -> None:
        self._raw = raw

    def get(self) -> int:
        raise tk.TclError(f'expected integer but got "{self._raw}"')


def _advanced_fake(app, *, batch_size_var) -> types.SimpleNamespace:
    """Build a SimpleNamespace carrying only what _save_and_close reads."""
    return types.SimpleNamespace(
        app=app,
        _vad_min_silence=_V(500),
        _vad_threshold=_V(0.5),
        _vad_speech_pad=_V(400),
        _format_vars={"srt": _V(True)},
        _batch_size=batch_size_var,
        _initial_prompt=_V("keep me"),
        _hotwords=_V(""),
        _auto_transcribe=_V(False),
        _sb_vars={},
        _cookies_browser=_V("(off)"),
        _filename_template=_V("{base}.{ext}"),
        _backend_display=_V("Faster-Whisper (local)"),
        _cloud_api_key=_V(""),
        _cloud_model=_V("gemini-3.5-flash"),
        _gcloud_credentials=_V(""),
        _gcloud_batch_mode=_V(False),
        _gcloud_bucket=_V(""),
        _gcloud_diarization=_V(False),
        _alignment=_V("none"),
        _hallucination_detect=_V(True),
        _demucs_enabled=_V(False),
        _ai_enabled=_V(False),
        _auto_chapters_enabled=_V(False),
        _voiceprint_enabled=_V(False),
        # No model change: chosen label maps back to the current slug.
        _model_display=_V("Large-v3"),
        _model_label_to_slug={"Large-v3": "large-v3"},
        _telemetry_opt_in=_V(False),
        _minimise_to_tray=_V(False),
        _watched_folder=_V(""),
        _watched_folder_enabled=_V(False),
        _teardown_mousewheel=lambda: None,
        destroy=lambda: None,
    )


def _fake_app(cfg) -> types.SimpleNamespace:
    svc = types.SimpleNamespace(stop_all=lambda: None)
    return types.SimpleNamespace(
        app_config=cfg,
        transcription_service=svc,
        log=lambda _m: None,
    )


def _base_cfg() -> dict:
    return {"whisper_model": "large-v3", "batch_size": 12}


@pytest.mark.parametrize("raw", ["", "abc", "  ", "8x"])
def test_save_survives_nonnumeric_batch_size(monkeypatch: Any, raw: str) -> None:
    """Save must not crash and must keep the prior batch_size + other edits."""
    from app.dialogs import advanced as adv

    saved = {"count": 0}
    monkeypatch.setattr(
        adv, "save_config",
        lambda _cfg: saved.__setitem__("count", saved["count"] + 1),
    )

    cfg = _base_cfg()
    app = _fake_app(cfg)
    dlg = _advanced_fake(app, batch_size_var=_BadIntVar(raw))

    # Must NOT raise (pre-fix this propagated a TclError out of the callback).
    adv.AdvancedDialog._save_and_close(dlg)  # type: ignore[arg-type]

    # Falls back to the prior saved value (not lost, not defaulted to 16).
    assert cfg["batch_size"] == 12
    # save_config still ran -> the user's OTHER edits were persisted.
    assert saved["count"] == 1
    assert cfg["initial_prompt"] == "keep me"


def test_save_falls_back_to_default_when_no_prior(monkeypatch: Any) -> None:
    """With no prior batch_size in cfg, fall back to the 16 default."""
    from app.dialogs import advanced as adv

    monkeypatch.setattr(adv, "save_config", lambda _cfg: None)

    cfg = {"whisper_model": "large-v3"}  # no batch_size key
    app = _fake_app(cfg)
    dlg = _advanced_fake(app, batch_size_var=_BadIntVar(""))

    adv.AdvancedDialog._save_and_close(dlg)  # type: ignore[arg-type]

    assert cfg["batch_size"] == 16


def test_valid_batch_size_still_persisted(monkeypatch: Any) -> None:
    """A normal numeric value is saved unchanged (clamped to >= 1)."""
    from app.dialogs import advanced as adv

    monkeypatch.setattr(adv, "save_config", lambda _cfg: None)

    cfg = _base_cfg()
    app = _fake_app(cfg)
    dlg = _advanced_fake(app, batch_size_var=_V(24))

    adv.AdvancedDialog._save_and_close(dlg)  # type: ignore[arg-type]

    assert cfg["batch_size"] == 24
