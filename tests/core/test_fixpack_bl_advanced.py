"""Regression test for AdvancedDialog 'Download now' mousewheel teardown.

``_download_selected_model`` closes the dialog with ``self.destroy()`` after
the user clicks "Download now". The two other close paths (_save_and_close /
_on_close) call ``_teardown_mousewheel()`` first to drop the GLOBAL
``bind_all("<MouseWheel>")`` registered on canvas <Enter>; the <Leave> unbind
only fires while the dialog stays open, so closing via "Download now" while
the pointer is over the canvas would otherwise leave a bind_all pointing at a
destroyed widget -- a stray callback on every later scroll.

These run against a SimpleNamespace fake with stub Vars -- no real Tk root, no
network, no model.
"""
from __future__ import annotations

import types
from typing import Any


class _V:
    """Minimal stand-in for a Tk *Var: .get() returns a fixed value."""

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def slug_map_label(slug_map, slug):
    for label, s in slug_map.items():
        if s == slug:
            return label
    return ""


def _fake_dialog(app, *, slug, slug_map, calls):
    """SimpleNamespace carrying only what _download_selected_model touches.

    ``calls`` is an ordered list each stubbed method appends its name to, so
    a test can assert teardown happens BEFORE destroy.
    """
    return types.SimpleNamespace(
        app=app,
        _model_display=_V(slug_map_label(slug_map, slug)),
        _model_label_to_slug=slug_map,
        _teardown_mousewheel=lambda: calls.append("teardown"),
        grab_release=lambda: calls.append("grab_release"),
        destroy=lambda: calls.append("destroy"),
    )


def _fake_app(cfg):
    after_calls = {"count": 0}

    def _after(_delay, fn):
        after_calls["count"] += 1
        # Do NOT invoke fn -- we don't want download_model_now to run.

    app = types.SimpleNamespace(
        app_config=cfg,
        log=lambda _m: None,
        after=_after,
        download_model_now=lambda: None,
    )
    return app, after_calls


def test_download_now_tears_down_mousewheel_before_destroy(monkeypatch: Any) -> None:
    from app.dialogs import advanced as adv

    monkeypatch.setattr(adv, "save_config", lambda _cfg: None)
    monkeypatch.setattr(
        adv, "catalog_resolve_entry",
        lambda _cfg, slug: {"name": slug, "url": "u", "md5": "m"},
    )

    cfg = {"whisper_model": "large-v3"}
    app, after_calls = _fake_app(cfg)
    calls: list[str] = []
    slug_map = {"Medium [needs download]": "medium"}
    dlg = _fake_dialog(app, slug=slug_map["Medium [needs download]"],
                       slug_map=slug_map, calls=calls)
    # Force the "not yet downloaded" branch so the close path runs.
    dlg._model_downloaded = lambda _s: False  # type: ignore[attr-defined]

    adv.AdvancedDialog._download_selected_model(dlg)  # type: ignore[arg-type]

    assert "teardown" in calls, (
        "Download now must tear down the global mousewheel binds before destroy"
    )
    assert "destroy" in calls
    assert calls.index("teardown") < calls.index("destroy"), (
        "teardown must run BEFORE destroy (else bind_all points at a "
        "destroyed widget)"
    )
    assert after_calls["count"] == 1  # the download modal was scheduled


def test_download_now_skips_when_already_downloaded(monkeypatch: Any) -> None:
    """When the model is already on disk, no close / teardown happens."""
    from app.dialogs import advanced as adv

    monkeypatch.setattr(adv, "save_config", lambda _cfg: None)
    monkeypatch.setattr(
        adv, "catalog_resolve_entry",
        lambda _cfg, slug: {"name": slug, "url": "u", "md5": "m"},
    )

    cfg = {"whisper_model": "large-v3"}
    app, after_calls = _fake_app(cfg)
    calls: list[str] = []
    slug_map = {"Large v3 [OK - downloaded]": "large-v3"}
    dlg = _fake_dialog(app, slug=slug_map["Large v3 [OK - downloaded]"],
                       slug_map=slug_map, calls=calls)
    dlg._model_downloaded = lambda _s: True  # type: ignore[attr-defined]

    adv.AdvancedDialog._download_selected_model(dlg)  # type: ignore[arg-type]

    assert calls == [], "already-downloaded path must not close the dialog"
    assert after_calls["count"] == 0
