"""Download + MD5-verify + extract the Whisper model.

Single model only (faster-whisper-large-v3). The URL and MD5
manifest URL live in ``DEFAULT_CONFIG["model"]``.

Public surface:

* :class:`DownloadCancelled` — raised when the cancel event fires.
* :func:`ensure_model` — idempotent download/verify/extract; returns
  the absolute path to the ready-to-load model folder.
* :func:`md5_file` — exposed for the diagnostics + tests.
"""
from __future__ import annotations

import hashlib
import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import requests


class DownloadCancelled(RuntimeError):
    """Raised by :func:`ensure_model` when the cancel event is set."""


def md5_file(
    path: str | Path,
    cancel_event: threading.Event | None = None,
) -> str:
    """Stream the file through MD5 in 1 MiB chunks; cancel-aware."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Model download cancelled")
            h.update(chunk)
    return h.hexdigest()


def _remove_path(path: str | Path) -> None:
    p = Path(path)
    if p.is_dir():
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()


def _fmt_bytes(value: float | int | None) -> str:
    v = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            return f"{v:.1f} {unit}" if unit != "B" else f"{int(v)} {unit}"
        v /= 1024
    return f"{v:.1f} TB"


def _fmt_time(seconds: float | int | None) -> str:
    if seconds is None:
        return "--:--"
    s = max(0, int(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02}:{m:02}:{sec:02}" if h else f"{m:02}:{sec:02}"


def _notify(
    progress_cb: Callable[[dict[str, Any]], None] | None,
    **payload: Any,
) -> None:
    if progress_cb:
        progress_cb(payload)


def _zip_name_from_url(zip_url: str) -> str:
    name = Path(unquote(urlparse(zip_url).path)).name
    return name or "model.zip"


def parse_md5_manifest(text: str) -> list[tuple[str, str]]:
    """Parse a coreutils-style ``md5sum`` manifest.

    Each non-empty line is ``<hex-digest>  <relative-path>``. Lines
    that don't fit the shape are silently skipped — a malformed
    manifest fails the *check* at verify time, not at parse time.
    """
    entries: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        checksum, path = parts
        # Strip the leading `*` (binary-mode marker) + normalise slashes.
        path = path.lstrip("*").replace("\\", "/")
        if path.startswith("./"):
            path = path[2:]
        entries.append((checksum.lower(), path))
    return entries


def _download_zip(
    zip_url: str,
    zip_path: Path,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """HTTP GET with byte-range resume + UI-friendly progress events.

    On a 416 from the server (range outside file size) we assume the
    file is already fully downloaded and return the existing path.
    """
    existing = zip_path.stat().st_size if zip_path.exists() else 0
    headers: dict[str, str] = {}
    mode = "wb"
    if existing:
        headers["Range"] = f"bytes={existing}-"
        mode = "ab"

    started = time.time()
    downloaded = existing
    with requests.get(zip_url, stream=True, headers=headers, timeout=(10, 30)) as r:
        if existing and r.status_code == 416:
            _notify(
                progress_cb,
                phase="download",
                status="Existing model archive found",
                downloaded=existing,
                total=existing,
                speed=0,
                remaining=0,
                percent=100,
                detail=f"{_fmt_bytes(existing)} already downloaded",
            )
            return zip_path

        r.raise_for_status()

        if existing and r.status_code != 206:
            existing = 0
            downloaded = 0
            mode = "wb"

        content_length = int(r.headers.get("content-length") or 0)
        total = existing + content_length if content_length else 0

        with open(zip_path, mode) as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if cancel_event and cancel_event.is_set():
                    raise DownloadCancelled("Model download cancelled")
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                elapsed = max(0.001, time.time() - started)
                speed = (downloaded - existing) / elapsed
                remaining = (
                    (total - downloaded) / speed if total and speed else None
                )
                percent = int((downloaded / total) * 100) if total else 0
                _notify(
                    progress_cb,
                    phase="download",
                    status="Downloading model...",
                    downloaded=downloaded,
                    total=total,
                    speed=speed,
                    remaining=remaining,
                    percent=percent,
                    detail=(
                        f"{_fmt_bytes(downloaded)} / "
                        f"{_fmt_bytes(total) if total else 'unknown'} at "
                        f"{_fmt_bytes(speed)}/s, ETA {_fmt_time(remaining)}"
                    ),
                )
    return zip_path


def _verify_extracted_files(
    cache_dir: Path,
    md5_url: str,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> list[tuple[str, str, str]]:
    """Fetch the MD5 manifest and verify every file under ``cache_dir``.

    Returns a list of ``(relative_path, expected, actual)`` tuples for
    any file that's missing or whose checksum doesn't match.
    """
    response = requests.get(md5_url, timeout=(10, 30))
    response.raise_for_status()
    entries = parse_md5_manifest(response.text)
    if not entries:
        raise RuntimeError("MD5 manifest does not contain any files")

    cache_root = cache_dir.resolve()
    mismatches: list[tuple[str, str, str]] = []

    for index, (expected, relative_path) in enumerate(entries, 1):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Model download cancelled")

        file_path = (cache_dir / relative_path).resolve()
        try:
            file_path.relative_to(cache_root)
        except ValueError:
            raise RuntimeError(
                f"Unsafe MD5 manifest path: {relative_path}"
            )

        if status_cb:
            status_cb(f"Checking MD5 {index}/{len(entries)}: {relative_path}")
        _notify(
            progress_cb,
            phase="verify",
            status=f"Checking MD5 {index}/{len(entries)}",
            percent=int((index - 1) / len(entries) * 100),
            detail=relative_path,
        )

        if not file_path.exists():
            mismatches.append((relative_path, expected, "missing"))
            continue

        actual = md5_file(file_path, cancel_event).lower()
        if actual != expected:
            mismatches.append((relative_path, expected, actual))

    _notify(
        progress_cb,
        phase="verify",
        status="MD5 verification complete",
        percent=100,
        detail=f"{len(entries) - len(mismatches)} / {len(entries)} files passed",
    )
    return mismatches


def ensure_model(
    config: dict[str, Any],
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    """Idempotent: download + extract + MD5-verify the model.

    Returns the absolute path of the model folder. Safe to call on
    every startup — when the model is already on disk and passes MD5,
    this is a quick checksum-only pass.

    MD5 mismatches trigger a full restart: zip + folder both wiped,
    download from byte 0.
    """
    model = config["model"]
    model_path = Path(config["model_path"])
    zip_url = model["url"]
    md5_url = model["md5"]

    cache_dir = model_path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)

    zip_path = cache_dir / _zip_name_from_url(zip_url)

    if model_path.exists():
        if status_cb:
            status_cb("Model already installed. Verifying MD5...")
        mismatches = _verify_extracted_files(
            cache_dir, md5_url, status_cb, progress_cb, cancel_event,
        )
        if not mismatches:
            _remove_path(zip_path)
            if status_cb:
                status_cb("Model already installed")
            _notify(
                progress_cb,
                phase="installed",
                status="Model already installed",
                percent=100,
            )
            return str(model_path)
        if status_cb:
            status_cb(
                "Installed model MD5 mismatch. Restarting download from zero..."
            )
        _remove_path(zip_path)
        _remove_path(model_path)

    while True:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Model download cancelled")

        if status_cb:
            status_cb("Downloading model...")
        _download_zip(zip_url, zip_path, progress_cb, cancel_event)

        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Model download cancelled")

        if status_cb:
            status_cb("Extracting model...")
        _notify(
            progress_cb,
            phase="extract",
            status="Extracting model...",
            percent=100,
            detail="Unpacking downloaded archive",
        )
        _remove_path(model_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(cache_dir)

        if not model_path.exists():
            raise RuntimeError(f"Extracted model folder missing: {model_path}")

        if status_cb:
            status_cb("Verifying extracted model files...")
        mismatches = _verify_extracted_files(
            cache_dir, md5_url, status_cb, progress_cb, cancel_event,
        )
        if not mismatches:
            _remove_path(zip_path)
            break

        if status_cb:
            status_cb(
                "MD5 mismatch. Deleting archive + folder; restarting download."
            )
        _notify(
            progress_cb,
            phase="restart",
            status="MD5 mismatch. Restarting download from zero...",
            percent=0,
            detail=f"{len(mismatches)} file checksum(s) failed",
        )
        _remove_path(zip_path)
        _remove_path(model_path)

    if status_cb:
        status_cb("Model ready")
    _notify(
        progress_cb,
        phase="ready",
        status="Model ready",
        percent=100,
        detail="Download complete",
    )
    return str(model_path)


def is_model_on_disk(config: dict[str, Any]) -> bool:
    """Cheap existence check — used by the App to decide whether to
    fire the download dialog before the loading dialog on first
    Transcribe click.
    """
    p = Path((config.get("model_path") or "").strip())
    if not p:
        return False
    return p.exists() and p.is_dir()
