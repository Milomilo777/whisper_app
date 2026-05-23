"""Resolve where bundled resources (bin/, faster_whisper assets) live.

Three runtime contexts:

  * onefile pyinstaller exe  ->  sys._MEIPASS (a temp extract dir)
  * onedir  pyinstaller exe  ->  dirname(sys.executable)
  * python source            ->  repo root (parent of this file's parent)

Use ``resource_base()`` for anything bundled at build time. Anything
that must persist between runs (user config, model cache) goes under
platformdirs paths in ``core.config``, not here.
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


def bundled_binary(name: str) -> str | None:
    """Absolute path to a bundled binary, or ``None`` if not bundled.

    On Windows we append ``.exe`` to the lookup name; on POSIX the
    name is used verbatim. Previously this returned the bare name
    on miss, which made callers feed an unresolved PATH-relative
    name into ``os.path.isfile`` (always False) and ``subprocess.run``
    (relies on PATH lookup with confusing error if absent). The
    contract is now explicit: ``None`` means "use shutil.which() at
    the call site, you decide whether PATH-fallback is acceptable"
    (audit P1-11).
    """
    exe = f"{name}.exe" if os.name == "nt" else name
    candidate = os.path.join(bin_dir(), exe)
    if os.path.isfile(candidate):
        return candidate
    return None
