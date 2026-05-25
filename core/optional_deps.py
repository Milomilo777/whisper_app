"""On-demand optional dependencies.

Heavy optional features — stable-ts word-alignment refinement and the
openai-whisper backend — pull in PyTorch (~700 MB), so they are NOT
bundled in the slim distribution. They are pip-installed on first use
into a user-writable directory that is added to ``sys.path``, mirroring
the on-demand Whisper-model download. This keeps the base install small
(~800 MB instead of ~1.5 GB) while every feature stays available.

The extras dir lives under the user's cache (writable without admin), so
this works for both the Program-Files install and the Portable build.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
from typing import Callable

from .config import user_cache_dir

# Serialises on-demand installs: two transcribes that both need the
# same feature can fire near-simultaneously, and two `pip install
# --target` runs into the same dir race and can leave a half-written
# package tree. The lock makes the second caller wait, then short-
# circuit on the now-present package.
_install_lock = threading.Lock()

# feature key -> (import name to probe, [pip packages to install])
FEATURES: dict[str, tuple[str, list[str]]] = {
    "alignment": ("stable_whisper", ["stable-ts"]),      # pulls torch
    "whisper_backend": ("whisper", ["openai-whisper"]),  # pulls torch
}


def extras_dir() -> str:
    """User-writable dir where on-demand packages are installed."""
    return os.path.join(str(user_cache_dir()), "pylibs")


def activate() -> None:
    """Put the extras dir on sys.path so on-demand packages import.

    Idempotent; call once at startup and after a successful install.
    """
    d = extras_dir()
    if os.path.isdir(d) and d not in sys.path:
        sys.path.insert(0, d)


def packages_for(feature: str) -> list[str]:
    return list(FEATURES.get(feature, ("", []))[1])


def is_available(feature: str) -> bool:
    """True iff the feature's top-level import resolves (bundled OR
    previously installed on-demand). Never raises."""
    activate()
    module = FEATURES.get(feature, ("", []))[0]
    if not module:
        return False
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:  # noqa: BLE001 — find_spec can raise on broken installs
        return False


def install(feature: str, log_cb: Callable[[str], None] | None = None) -> bool:
    """pip-install the feature's packages into the user extras dir.

    Streams pip output to ``log_cb``. Returns True on success (exit 0) and
    activates the dir so the package imports immediately.
    """
    pkgs = packages_for(feature)
    if not pkgs:
        return False
    with _install_lock:
        # A concurrent caller may have installed it while we waited on
        # the lock — don't run a second redundant (and racing) pip.
        if is_available(feature):
            return True
        target = extras_dir()
        os.makedirs(target, exist_ok=True)
        cmd = [sys.executable, "-m", "pip", "install", "--target", target, "--upgrade", *pkgs]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line and log_cb:
                log_cb(line)
        if proc.wait() == 0:
            activate()
            return True
        return False
