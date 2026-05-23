"""Startup self-diagnostics.

Each check returns a :class:`CheckResult`. The App runs the full
suite at launch and again from Help → Diagnose. A failed check is
shown to the user as ``"Issue: <name>. Try: <hint>"``.
"""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import load_config, user_config_dir
from .hub import is_hub_configured
from .paths import bundled_binary


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    suggestion: str = ""

    def format(self) -> str:
        status = "OK" if self.ok else "FAIL"
        body = f"[{status}] {self.name}: {self.detail}"
        if not self.ok and self.suggestion:
            body += f"\n        → {self.suggestion}"
        return body


CheckFn = Callable[[], CheckResult]


def _check_ffmpeg() -> CheckResult:
    path = bundled_binary("ffmpeg")
    if not os.path.isfile(path):
        # bundled_binary returns the bare name when not found, which
        # may or may not resolve on PATH.
        resolved = shutil.which(path) or ""
        if not resolved:
            return CheckResult(
                "ffmpeg",
                False,
                "ffmpeg binary not found in bin/ or on PATH.",
                "Reinstall the app — the bundled binary should sit in bin/ffmpeg.exe.",
            )
        path = resolved
    return CheckResult("ffmpeg", True, f"found at {path}")


def _check_ffprobe() -> CheckResult:
    path = bundled_binary("ffprobe")
    if not os.path.isfile(path):
        resolved = shutil.which(path) or ""
        if not resolved:
            return CheckResult(
                "ffprobe",
                False,
                "ffprobe binary not found in bin/ or on PATH.",
                "Reinstall the app — the bundled binary should sit in bin/ffprobe.exe.",
            )
        path = resolved
    # Smoke: it should -version cleanly.
    try:
        kwargs: dict[str, Any] = {
            "capture_output": True, "text": True, "timeout": 5,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        r = subprocess.run([path, "-version"], **kwargs)
    except (OSError, subprocess.TimeoutExpired) as e:
        return CheckResult(
            "ffprobe", False, f"ffprobe -version failed: {e}",
            "Reinstall the app — the bundled binary is unusable on this machine.",
        )
    if r.returncode != 0:
        return CheckResult(
            "ffprobe", False,
            f"ffprobe -version returned {r.returncode}",
            "Reinstall the app — the bundled binary is broken.",
        )
    return CheckResult("ffprobe", True, f"OK ({path})")


def _check_disk_writable() -> CheckResult:
    target = user_config_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=True, dir=str(target),
        ) as f:
            f.write("ok")
    except OSError as e:
        return CheckResult(
            "disk_writable", False,
            f"could not write to {target}: {e}",
            "Make sure your user profile disk is not full and is writable.",
        )
    return CheckResult("disk_writable", True, f"can write to {target}")


def _check_config_valid() -> CheckResult:
    try:
        cfg = load_config()
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            "config", False, f"config.json could not be loaded: {e}",
            "Delete the file at %APPDATA%/WhisperProjectBasic/config.json to reset.",
        )
    missing = [k for k in ("model", "model_path", "output_formats") if k not in cfg]
    if missing:
        return CheckResult(
            "config", False, f"missing keys: {missing!r}",
            "Delete the config file to recreate it from defaults.",
        )
    return CheckResult("config", True, "valid")


def _check_hub_configured() -> CheckResult:
    cfg = load_config()
    if is_hub_configured(cfg):
        return CheckResult(
            "hub_folder", True,
            f"hub at {cfg.get('hub_folder')}",
        )
    return CheckResult(
        "hub_folder", True,
        "not yet picked — first-run dialog will fire",
    )


def _check_model_accessible() -> CheckResult:
    cfg = load_config()
    path = (cfg.get("model_path") or "").strip()
    if not path:
        return CheckResult(
            "model_present", True,
            "model not downloaded yet — download will fire on first Transcribe.",
        )
    p = Path(path)
    if not p.exists():
        return CheckResult(
            "model_present", True,
            f"model folder not yet present at {p} — download will fire on first Transcribe.",
        )
    if not p.is_dir():
        return CheckResult(
            "model_present", False,
            f"{p} exists but is not a directory.",
            "Delete the file and let the model downloader recreate it.",
        )
    # Look for a model.bin (faster-whisper layout). Missing it would
    # cause WhisperModel(...) to throw on load.
    if not any(p.glob("**/model.bin")):
        return CheckResult(
            "model_present", False,
            f"no model.bin found under {p}.",
            "Delete the model folder and re-trigger the download.",
        )
    return CheckResult(
        "model_present", True, f"model.bin found under {p}",
    )


def _check_faster_whisper_importable() -> CheckResult:
    try:
        importlib.import_module("faster_whisper")
    except ImportError as e:
        return CheckResult(
            "faster_whisper", False, f"import failed: {e}",
            "Run `pip install -r requirements.txt`.",
        )
    return CheckResult("faster_whisper", True, "importable")


def _check_python_version() -> CheckResult:
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 11):
        return CheckResult(
            "python_version", False,
            f"running Python {major}.{minor}",
            "Use Python 3.11 or newer (3.11 / 3.12 supported).",
        )
    return CheckResult(
        "python_version", True, f"Python {major}.{minor}",
    )


CHECKS: list[CheckFn] = [
    _check_python_version,
    _check_faster_whisper_importable,
    _check_ffmpeg,
    _check_ffprobe,
    _check_disk_writable,
    _check_config_valid,
    _check_hub_configured,
    _check_model_accessible,
]


def run_all() -> list[CheckResult]:
    """Run the full suite and return the results in order."""
    out: list[CheckResult] = []
    for fn in CHECKS:
        try:
            out.append(fn())
        except Exception as e:  # noqa: BLE001
            out.append(CheckResult(
                fn.__name__.removeprefix("_check_"),
                False,
                f"check itself crashed: {e}",
                "Report this — a self-check should not raise.",
            ))
    return out


def first_failure(results: list[CheckResult]) -> CheckResult | None:
    """Return the first FAIL in ``results``, else None."""
    for r in results:
        if not r.ok:
            return r
    return None


def format_report(results: list[CheckResult]) -> str:
    """Render the results as a copy-pasteable plain-text block."""
    lines = ["Whisper Project — basic — diagnostics report", ""]
    for r in results:
        lines.append(r.format())
    return "\n".join(lines) + "\n"
