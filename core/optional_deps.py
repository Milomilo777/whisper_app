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

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable

from .config import user_cache_dir

# Hard cap on a single on-demand pip install. A stalled PyPI / proxy
# black-hole would otherwise leave the reader loop (and the modal that
# waits on it) blocked forever with no way to abort.
DEFAULT_INSTALL_TIMEOUT_S = 1800.0

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


def install(
    feature: str,
    log_cb: Callable[[str], None] | None = None,
    cancel_event: "threading.Event | None" = None,
    timeout: float = DEFAULT_INSTALL_TIMEOUT_S,
) -> bool:
    """pip-install the feature's packages into the user extras dir.

    Streams pip output to ``log_cb``. Returns True only when the install
    completes AND the feature actually imports.

    Robustness (audit findings [10]/[11]):

    * pip installs into a TEMP staging dir on the same volume and is merged
      into the extras dir only on a clean exit, so a failed / cancelled /
      timed-out install never leaves a half-written package tree that
      ``is_available()`` (a cheap ``find_spec``) would report as present —
      which previously short-circuited the next install and then crashed
      the worker on the real import.
    * ``cancel_event`` and ``timeout`` bound the run: a stalled pip is
      terminated (and its staging tree removed) instead of blocking the
      waiting modal forever.
    """
    pkgs = packages_for(feature)
    if not pkgs:
        return False
    with _install_lock:
        # A concurrent caller may have installed it while we waited on
        # the lock — don't run a second redundant (and racing) pip.
        if is_available(feature):
            return True
        final_target = extras_dir()
        os.makedirs(final_target, exist_ok=True)
        parent = os.path.dirname(final_target) or None
        staging = tempfile.mkdtemp(prefix="pylibs-stage-", dir=parent)
        cmd = [
            sys.executable, "-m", "pip", "install",
            "--target", staging, "--upgrade", *pkgs,
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(staging, ignore_errors=True)
            if log_cb:
                log_cb(f"Could not start pip: {e}")
            return False

        # Stream pip output on a daemon thread so the main thread can poll
        # for cancellation / timeout (a blocking readline can't be
        # interrupted, so we don't read inline).
        def _pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if line and log_cb:
                    log_cb(line)

        reader = threading.Thread(target=_pump, name=f"pip-{feature}", daemon=True)
        reader.start()

        deadline = (time.time() + timeout) if timeout else None
        aborted = False
        while True:
            try:
                proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancel_event is not None and cancel_event.is_set():
                if log_cb:
                    log_cb("Install cancelled.")
                aborted = True
                break
            if deadline is not None and time.time() > deadline:
                if log_cb:
                    log_cb(f"Install timed out after {int(timeout)}s.")
                aborted = True
                break

        if aborted:
            for _stop in (proc.terminate, proc.kill):
                try:
                    _stop()
                    proc.wait(timeout=5)
                    break
                except Exception:  # noqa: BLE001
                    continue
            reader.join(timeout=2)
            shutil.rmtree(staging, ignore_errors=True)
            return False

        reader.join(timeout=5)
        if proc.returncode != 0:
            # Non-zero exit — discard the staging tree only; never touch
            # extras_dir (a sibling feature may already live there).
            shutil.rmtree(staging, ignore_errors=True)
            return False

        # Merge the freshly-installed tree into the extras dir, then drop
        # the staging copy. dirs_exist_ok merges over an existing sibling.
        try:
            shutil.copytree(staging, final_target, dirs_exist_ok=True)
        except Exception as e:  # noqa: BLE001
            if log_cb:
                log_cb(f"Could not finalise install: {e}")
            shutil.rmtree(staging, ignore_errors=True)
            return False
        shutil.rmtree(staging, ignore_errors=True)

        activate()
        # Verify the feature actually imports now (not just that a partial
        # top-level dir exists) before reporting success.
        importlib.invalidate_caches()
        return is_available(feature)
