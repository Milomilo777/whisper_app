"""Resolve where bundled resources (bin/, faster_whisper assets) live.

Three runtime contexts:

  * onefile pyinstaller exe  ->  sys._MEIPASS (a temp extract dir)
  * onedir  pyinstaller exe  ->  dirname(sys.executable)
  * python source            ->  repo root (parent of this file's parent)

Use ``resource_base()`` for anything that was bundled into the exe at
build time. Anything that has to *persist* between runs (user config,
history db, downloaded model cache) belongs under platformdirs, not
here.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_base() -> str:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return str(meipass)
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return str(Path(__file__).resolve().parent.parent)


def bin_dir() -> str:
    return os.path.join(resource_base(), "bin")


def bundled_binary(name: str) -> str:
    """Absolute path to a bundled binary; falls back to PATH lookup name."""
    exe = f"{name}.exe" if os.name == "nt" else name
    candidate = os.path.join(bin_dir(), exe)
    return candidate if os.path.isfile(candidate) else name
