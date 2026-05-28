from __future__ import annotations

import hashlib
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import unquote, urlparse

import requests


class DownloadCancelled(RuntimeError):
    pass


# Bound the download/verify retry loop. A permanently-bad mirror or a
# captive-portal MD5 body would otherwise re-download the whole ~3 GB
# archive forever (the only escape was the modal Cancel button — useless
# on an unattended / auto-transcribe run). After this many failed
# attempts we raise so the UI reports a real, terminal error.
MAX_DOWNLOAD_ATTEMPTS = 3

# A valid md5sum line begins with a 32-hex-char digest. Rejecting
# anything else stops an HTML error page (captive portal / proxy) from
# being mis-parsed as a manifest and driving an endless re-download.
_MD5_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


# ---------------------------------------------------------------- model picker
#
# v0.8 — pick one of several pre-bundled faster-whisper variants from
# the Advanced dialog. Each entry resolves to the ``model`` sub-dict
# (name + url + md5) the rest of this module already consumes.
#
# Mirror URLs follow the existing smch.ir convention so adding a new
# entry is a one-line change. ``approx_size_gb`` is shown in the
# Advanced dropdown so the user knows the install cost up front.

MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "large-v3": {
        "label": "Large v3 — best accuracy (default, ~3 GB)",
        "name": "faster-whisper-large-v3",
        "url": "https://smch.ir/models/models--Systran--faster-whisper-large-v3.zip",
        "md5": "https://smch.ir/models/models--Systran--faster-whisper-large-v3.zip.md5",
        "approx_size_gb": 3.0,
    },
    "large-v3-turbo": {
        "label": "Large v3 Turbo — ~5× faster, similar accuracy (~1.6 GB)",
        "name": "faster-whisper-large-v3-turbo",
        "url": "https://smch.ir/models/models--Systran--faster-whisper-large-v3-turbo.zip",
        "md5": "https://smch.ir/models/models--Systran--faster-whisper-large-v3-turbo.zip.md5",
        "approx_size_gb": 1.6,
    },
    "distil-large-v3.5": {
        "label": "Distil Large v3.5 — fastest English-only (~1.5 GB)",
        "name": "faster-distil-whisper-large-v3.5",
        "url": "https://smch.ir/models/models--Systran--faster-distil-whisper-large-v3.5.zip",
        "md5": "https://smch.ir/models/models--Systran--faster-distil-whisper-large-v3.5.zip.md5",
        "approx_size_gb": 1.5,
    },
}


DEFAULT_MODEL_SLUG = "large-v3"


def list_models() -> list[tuple[str, str]]:
    """Return ``[(slug, label), ...]`` for the UI dropdown."""
    return [(slug, entry["label"]) for slug, entry in MODEL_REGISTRY.items()]


def resolve_model_entry(slug: str) -> dict[str, Any] | None:
    """Return ``{name, url, md5}`` for a registry slug, or ``None`` when unknown.

    The returned dict shape matches ``DEFAULT_CONFIG["model"]`` so the
    caller can assign it directly to ``config["model"]`` and the rest
    of the codebase (``ensure_model``, the cache-dir fallback) keeps
    working without changes.
    """
    entry = MODEL_REGISTRY.get(slug)
    if entry is None:
        return None
    return {"name": entry["name"], "url": entry["url"], "md5": entry["md5"]}

def md5_file(path: str | Path, cancel_event: threading.Event | None = None) -> str:
    h=hashlib.md5()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Model download cancelled")
            h.update(chunk)
    return h.hexdigest()

def _remove_path(path: str | Path) -> None:
    path=Path(path)
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

def _fmt_bytes(value: float | int | None) -> str:
    value=float(value or 0)
    for unit in ("B","KB","MB","GB","TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value/=1024
    return f"{value:.1f} TB"

def _fmt_time(seconds: float | int | None) -> str:
    if seconds is None:
        return "--:--"
    seconds=max(0,int(seconds))
    h=seconds//3600
    m=(seconds%3600)//60
    s=seconds%60
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"

def _notify(progress_cb: Callable[[dict[str, Any]], None] | None, **payload: Any) -> None:
    if progress_cb:
        progress_cb(payload)

def _zip_name_from_url(zip_url: str) -> str:
    name=Path(unquote(urlparse(zip_url).path)).name
    return name or "model.zip"

def _parse_md5_manifest(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in text.splitlines():
        line=line.strip()
        if not line:
            continue

        parts=line.split(None,1)
        if len(parts)!=2:
            continue

        checksum,path=parts
        checksum=checksum.lower()
        # Skip lines whose first token isn't a 32-hex md5 digest — an
        # HTML/captive-portal body otherwise yields bogus "entries" that
        # always mismatch and drive the (now-bounded) re-download loop.
        if not _MD5_HEX_RE.match(checksum):
            continue
        path=path.lstrip("*").replace("\\","/")
        if path.startswith("./"):
            path=path[2:]
        entries.append((checksum,path))
    return entries

def _download_zip(
    zip_url: str,
    zip_path: Path,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    existing=zip_path.stat().st_size if zip_path.exists() else 0
    headers={}
    mode="wb"
    if existing:
        headers["Range"]=f"bytes={existing}-"
        mode="ab"

    started=time.time()
    downloaded=existing
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
            existing=0
            downloaded=0
            mode="wb"

        content_length=int(r.headers.get("content-length") or 0)
        total=existing + content_length if content_length else 0

        with open(zip_path,mode) as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if cancel_event and cancel_event.is_set():
                    raise DownloadCancelled("Model download cancelled")
                if not chunk:
                    continue

                f.write(chunk)
                downloaded += len(chunk)
                elapsed=max(0.001,time.time()-started)
                speed=(downloaded-existing)/elapsed
                remaining=(total-downloaded)/speed if total and speed else None
                percent=int((downloaded/total)*100) if total else 0

                _notify(
                    progress_cb,
                    phase="download",
                    status="Downloading model...",
                    downloaded=downloaded,
                    total=total,
                    speed=speed,
                    remaining=remaining,
                    percent=percent,
                    detail=f"{_fmt_bytes(downloaded)} / {_fmt_bytes(total) if total else 'unknown'} at {_fmt_bytes(speed)}/s, ETA {_fmt_time(remaining)}",
                )

    return zip_path

def _verify_extracted_files(
    cache_dir: Path,
    md5_url: str,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> list[tuple[str, str, str]]:
    response=requests.get(md5_url, timeout=(10, 30))
    response.raise_for_status()
    entries=_parse_md5_manifest(response.text)
    if not entries:
        raise RuntimeError("MD5 manifest does not contain any files")

    cache_root=cache_dir.resolve()
    mismatches: list[tuple[str, str, str]] = []

    for index,(expected,relative_path) in enumerate(entries,1):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Model download cancelled")

        file_path=(cache_dir / relative_path).resolve()
        try:
            file_path.relative_to(cache_root)
        except ValueError:
            raise RuntimeError(f"Unsafe MD5 manifest path: {relative_path}")

        if status_cb: status_cb(f"Checking MD5 {index}/{len(entries)}: {relative_path}")
        _notify(
            progress_cb,
            phase="verify",
            status=f"Checking MD5 {index}/{len(entries)}",
            percent=int((index-1)/len(entries)*100),
            detail=relative_path,
        )

        if not file_path.exists():
            actual="missing"
            mismatches.append((relative_path,expected,actual))
            if status_cb:
                status_cb(f"MD5 CHECK: {relative_path} expected={expected} actual={actual}")
                status_cb(f"Checksum difference: {relative_path} expected={expected} actual={actual}")
            continue

        actual=md5_file(file_path, cancel_event).lower()
        if status_cb: status_cb(f"MD5 CHECK: {relative_path} expected={expected} actual={actual}")
        if actual == expected:
            if status_cb: status_cb(f"MD5 OK: {relative_path}")
        else:
            mismatches.append((relative_path,expected,actual))
            if status_cb: status_cb(f"Checksum difference: {relative_path} expected={expected} actual={actual}")

    _notify(
        progress_cb,
        phase="verify",
        status="MD5 verification complete",
        percent=100,
        detail=f"{len(entries)-len(mismatches)} / {len(entries)} files passed",
    )
    return mismatches

def ensure_model(
    config: dict[str, Any],
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    model=config["model"]
    model_path=Path(config["model_path"])
    zip_url=model["url"]
    md5_url=model["md5"]

    cache_dir=model_path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)

    zip_path=cache_dir / _zip_name_from_url(zip_url)

    if model_path.exists():
        if status_cb: status_cb("Model already installed. Verifying MD5...")
        mismatches=_verify_extracted_files(cache_dir, md5_url, status_cb, progress_cb, cancel_event)
        if not mismatches:
            _remove_path(zip_path)
            if status_cb: status_cb("Model already installed")
            _notify(progress_cb, phase="installed", status="Model already installed", percent=100)
            return str(model_path)

        if status_cb: status_cb("Installed model MD5 mismatch. Restarting download from zero...")
        _remove_path(zip_path)
        _remove_path(model_path)

    last_mismatches: list[tuple[str, str, str]] = []
    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Model download cancelled")

        if status_cb: status_cb("Downloading model...")
        _download_zip(zip_url, zip_path, progress_cb, cancel_event)

        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Model download cancelled")

        if status_cb: status_cb("Extracting model...")
        _notify(progress_cb, phase="extract", status="Extracting model...", percent=100, detail="Unpacking downloaded archive")
        _remove_path(model_path)
        with zipfile.ZipFile(zip_path,'r') as z:
            # Zip-slip guard: reject any member that would resolve OUTSIDE
            # cache_dir (e.g. a tampered archive with "..\\.." entries)
            # before extracting anything.
            _cache_resolved = Path(cache_dir).resolve()
            for _member in z.namelist():
                _target = (_cache_resolved / _member).resolve()
                if _target != _cache_resolved and _cache_resolved not in _target.parents:
                    raise RuntimeError(f"Unsafe path in model archive: {_member!r}")
            z.extractall(cache_dir)

        if not model_path.exists():
            raise RuntimeError(f"Extracted model folder missing: {model_path}")

        if status_cb: status_cb("Verifying extracted model files...")
        mismatches=_verify_extracted_files(cache_dir, md5_url, status_cb, progress_cb, cancel_event)
        if not mismatches:
            _remove_path(zip_path)
            break

        last_mismatches = mismatches
        _remove_path(zip_path)
        _remove_path(model_path)

        if attempt >= MAX_DOWNLOAD_ATTEMPTS:
            # Don't loop forever on a bad mirror / corrupt archive.
            break

        if status_cb:
            status_cb(
                f"MD5 mismatch (attempt {attempt}/{MAX_DOWNLOAD_ATTEMPTS}). "
                "Deleting model archive and folder, then restarting from zero..."
            )
        _notify(
            progress_cb,
            phase="restart",
            status=f"MD5 mismatch. Retrying ({attempt}/{MAX_DOWNLOAD_ATTEMPTS})...",
            percent=0,
            detail=f"{len(mismatches)} file checksum(s) failed",
        )

    if last_mismatches:
        sample = ", ".join(rel for _exp, _got, rel in last_mismatches[:5])
        more = "" if len(last_mismatches) <= 5 else f" (+{len(last_mismatches) - 5} more)"
        raise RuntimeError(
            f"Model download failed after {MAX_DOWNLOAD_ATTEMPTS} attempts: "
            f"{len(last_mismatches)} file checksum(s) still mismatched "
            f"[{sample}{more}]. The mirror may be serving a corrupt archive."
        )

    if status_cb: status_cb("Model ready")
    _notify(progress_cb, phase="ready", status="Model ready", percent=100, detail="Download complete")
    return str(model_path)
