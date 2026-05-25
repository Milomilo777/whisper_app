"""Layout-independent clipboard keys (Ctrl+C / V / X / A).

Tk's built-in bindings key off the Latin keysym, so paste/copy/cut/
select-all silently break under a non-Latin keyboard layout (Persian,
Arabic, Russian, …). The fix dispatches by the physical key's keycode
instead. These tests exercise the pure decision function
``App._clipboard_action`` (the binding + event_generate is the Tk part,
verified manually).
"""
from __future__ import annotations

import pytest

pytest.importorskip("tkinter")

from app.app import App


def test_latin_layout_defers_to_tk_default():
    # English layout already produces a/c/v/x — let Tk's own binding
    # handle it so we don't act twice.
    for ks, kc in (("v", 86), ("c", 67), ("x", 88), ("a", 65)):
        assert App._clipboard_action(ks, kc) is None


def test_uppercase_latin_also_defers():
    assert App._clipboard_action("V", 86) is None


def test_non_latin_layout_dispatches_by_keycode():
    # Persian layout: the physical V/C/X/A keys report non-Latin keysyms
    # but the same Windows keycodes — the clipboard action must still fire.
    assert App._clipboard_action("ر", 86) == "paste"
    assert App._clipboard_action("ذ", 67) == "copy"
    assert App._clipboard_action("ط", 88) == "cut"
    assert App._clipboard_action("ش", 65) == "selectall"


def test_non_clipboard_keys_return_none():
    assert App._clipboard_action("o", 79) is None    # Ctrl+O (Latin)
    assert App._clipboard_action("ن", 79) is None    # any layout, not a clipboard key
    assert App._clipboard_action("", 13) is None     # Enter, no keysym
