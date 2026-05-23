"""Services owned by the Tk app.

Each module here wraps a long-running side-effecting concern
(downloading media, future history / transcript export, ...) so the
Tk widgets can stay thin. Services post events back to the App on
the existing ``worker_events`` queue, which the App drains on its
Tk main thread.
"""
from __future__ import annotations
