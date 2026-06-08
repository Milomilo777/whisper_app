from __future__ import annotations

import errno
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


class ModelDestinationNotWritable(RuntimeError):
    """The model destination directory cannot be created or written.

    Raised when creating / extracting into the model folder fails with
    a permission error (Windows ``WinError 5`` "Access is denied" /
    POSIX ``EACCES``). The most common cause is an ``<app_dir>/hub``
    location under Program Files for a standard (non-admin) user. The
    UI catches this to offer a writable folder instead of showing the
    raw OS error string.

    ``directory`` carries the offending path for the UI message.
    """

    def __init__(self, directory: str | Path, message: str | None = None) -> None:
        self.directory = str(directory)
        super().__init__(
            message
            or f"Cannot write to the model folder: {self.directory}"
        )


# OSError.errno values that mean "you don't have permission here".
# EACCES is the POSIX form; on Windows, "Access is denied" (WinError 5)
# surfaces as a PermissionError whose .errno is EACCES, and rarer cases
# raise EPERM. We treat both as the not-writable signal.
_PERMISSION_ERRNOS = {errno.EACCES, errno.EPERM}


def _is_permission_error(exc: OSError) -> bool:
    """True when ``exc`` indicates a lack of write permission."""
    if isinstance(exc, PermissionError):
        return True
    return exc.errno in _PERMISSION_ERRNOS


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

# This is the BUILT-IN default catalog. It is the lowest-priority source —
# the online config (see core.config) may ADD or OVERRIDE entries under its
# ``model_catalog`` key, so new models can ship without an app update. Use
# ``catalog_models(config)`` / ``catalog_resolve_entry(config, slug)`` to read
# the merged effective catalog; the bare ``MODEL_REGISTRY`` / ``list_models``
# / ``resolve_model_entry`` helpers keep returning the built-ins only (still
# used as the offline fallback and by existing tests).
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
    # NOTE: this artifact may not exist on smch.ir yet — the URL/MD5
    # below follow the same naming convention as the entries above
    # (Systran's faster-whisper-medium). If the mirror 404s (or any
    # other download/verification failure occurs), ``ensure_model``
    # now automatically falls back to fetching the same model straight
    # from the HuggingFace Hub via ``_repo_id_from_url`` /
    # ``_download_via_huggingface``, so this entry works either way.
    # ~1.5 GB.
    "medium": {
        "label": "Medium — faster, lower accuracy (~1.5 GB)",
        "name": "faster-whisper-medium",
        "url": "https://smch.ir/models/models--Systran--faster-whisper-medium.zip",
        "md5": "https://smch.ir/models/models--Systran--faster-whisper-medium.zip.md5",
        "approx_size_gb": 1.5,
    },
}


DEFAULT_MODEL_SLUG = "large-v3"


def list_models() -> list[tuple[str, str]]:
    """Return ``[(slug, label), ...]`` for the UI dropdown (built-ins only)."""
    return [(slug, entry["label"]) for slug, entry in MODEL_REGISTRY.items()]


def resolve_model_entry(slug: str) -> dict[str, Any] | None:
    """Return ``{name, url, md5}`` for a built-in registry slug, or ``None``.

    The returned dict shape matches ``DEFAULT_CONFIG["model"]`` so the
    caller can assign it directly to ``config["model"]`` and the rest
    of the codebase (``ensure_model``, the cache-dir fallback) keeps
    working without changes.
    """
    entry = MODEL_REGISTRY.get(slug)
    if entry is None:
        return None
    return {"name": entry["name"], "url": entry["url"], "md5": entry["md5"]}


def _merged_catalog(config: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Built-in MODEL_REGISTRY overlaid with ``config['model_catalog']``.

    The online/local config may carry a ``model_catalog`` dict in the SAME
    shape as MODEL_REGISTRY (slug → {label, name, url, md5, approx_size_gb}).
    Each online slug is overlaid onto the built-in entry (or added new), so
    the catalog can grow / be re-pointed without an app update. A malformed
    catalog (not a dict, or non-dict entries) is ignored entry-by-entry so a
    bad online payload never breaks the picker — the built-ins still show.
    """
    merged: dict[str, dict[str, Any]] = {
        slug: dict(entry) for slug, entry in MODEL_REGISTRY.items()
    }
    extra = (config or {}).get("model_catalog")
    if not isinstance(extra, dict):
        return merged
    for slug, entry in extra.items():
        if not isinstance(slug, str) or not isinstance(entry, dict):
            continue
        # Require the fields ensure_model needs; skip anything incomplete.
        if not all(isinstance(entry.get(k), str) and entry.get(k)
                   for k in ("name", "url", "md5")):
            continue
        base = dict(merged.get(slug) or {})
        base.update(entry)
        base.setdefault("label", slug)
        base.setdefault("approx_size_gb", 0.0)
        merged[slug] = base
    return merged


def catalog_models(config: dict[str, Any] | None) -> list[tuple[str, str]]:
    """``[(slug, label), ...]`` from the MERGED catalog (built-ins + online).

    This is what the Advanced model picker should call so an online-added
    model appears without an app update.
    """
    return [(slug, entry.get("label") or slug)
            for slug, entry in _merged_catalog(config).items()]


def catalog_resolve_entry(
    config: dict[str, Any] | None, slug: str
) -> dict[str, Any] | None:
    """``{name, url, md5}`` for ``slug`` from the merged catalog, or ``None``."""
    entry = _merged_catalog(config).get(slug)
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

        try:
            zip_file=open(zip_path,mode)
        except OSError as e:
            if _is_permission_error(e):
                raise ModelDestinationNotWritable(zip_path.parent) from e
            raise
        with zip_file as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if cancel_event and cancel_event.is_set():
                    raise DownloadCancelled("Model download cancelled")
                if not chunk:
                    continue

                try:
                    f.write(chunk)
                except OSError as e:
                    if _is_permission_error(e):
                        raise ModelDestinationNotWritable(zip_path.parent) from e
                    raise
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

_MODEL_TOKEN_RE = re.compile(r"^models--(.+)$")


def _repo_id_from_url(zip_url: str) -> str | None:
    """Map a smch.ir zip URL/name to its HuggingFace ``Org/Repo`` id.

    The mirror zips are named ``models--<Org>--<Repo>.zip`` and that
    token encodes the exact HuggingFace ``repo_id`` whose
    ``snapshot_download`` cache layout the zip mirrors byte-for-byte
    (``cache_dir/models--<Org>--<Repo>/snapshots/<hash>/...``). This
    lets the fallback path target the correct upstream repo from the
    same registry entry, with no extra config. Returns ``None`` when
    the URL/name doesn't match the expected ``models--Org--Repo`` shape.

    Note: repo names can themselves contain dots (e.g.
    ``faster-distil-whisper-large-v3.5``), so the ``.zip`` suffix is
    stripped by name rather than by splitting on the first dot.
    """
    name = _zip_name_from_url(zip_url)
    if name.lower().endswith(".zip"):
        name = name[: -len(".zip")]

    match = _MODEL_TOKEN_RE.match(name)
    if not match:
        return None

    parts = match.group(1).split("--")
    if len(parts) < 2:
        return None

    org = parts[0]
    repo = "-".join(parts[1:])
    if not org or not repo:
        return None
    return f"{org}/{repo}"


def _download_via_huggingface(
    repo_id: str,
    cache_dir: Path,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    """Fetch ``repo_id`` straight from the HuggingFace Hub as a fallback.

    Used only when the smch.ir mirror is unavailable or its archive
    fails verification. ``snapshot_download`` writes into ``cache_dir``
    using the exact same ``models--Org--Repo/snapshots/<hash>/...``
    layout the mirror zips use, so the rest of the app keeps resolving
    the model folder unchanged. Returns ``True`` on success, ``False``
    on any failure (import error, network error, cancellation) — the
    caller decides how to report that.
    """
    if cancel_event and cancel_event.is_set():
        return False

    try:
        from huggingface_hub import snapshot_download
    except ImportError as e:
        if status_cb:
            status_cb(f"HuggingFace fallback unavailable: {e}")
        return False

    if status_cb:
        status_cb(
            f"Mirror unavailable — downloading {repo_id} from huggingface.co ..."
        )
    _notify(
        progress_cb,
        phase="download",
        status=f"Downloading {repo_id} from HuggingFace...",
        percent=0,
        detail="Mirror unavailable — using huggingface.co",
    )

    try:
        snapshot_download(repo_id=repo_id, cache_dir=str(cache_dir))
    except Exception as e:
        if status_cb:
            status_cb(f"HuggingFace download failed: {e}")
        return False

    if cancel_event and cancel_event.is_set():
        return False

    if status_cb:
        status_cb("Model downloaded from HuggingFace.")
    _notify(
        progress_cb,
        phase="download",
        status="Model downloaded from HuggingFace.",
        percent=100,
        detail=repo_id,
    )
    return True


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
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        if _is_permission_error(e):
            raise ModelDestinationNotWritable(cache_dir) from e
        raise

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

    mirror_error: BaseException | None = None
    try:
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
                try:
                    z.extractall(cache_dir)
                except OSError as e:
                    if _is_permission_error(e):
                        raise ModelDestinationNotWritable(cache_dir) from e
                    raise

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
    except (DownloadCancelled, ModelDestinationNotWritable):
        raise
    except Exception as e:
        # The smch.ir mirror failed for ANY reason — missing zip (404),
        # network error, or persistent MD5 mismatch. Before giving up,
        # try the same model straight from the HuggingFace Hub: the
        # registry's zip name encodes the exact upstream repo_id, and
        # snapshot_download writes the identical cache layout the mirror
        # zip would have, so the rest of the app keeps working unchanged.
        mirror_error = e
        repo_id = _repo_id_from_url(zip_url)
        if repo_id is None:
            raise

        if status_cb:
            status_cb(f"Mirror download failed ({e}). Trying HuggingFace fallback...")
        _remove_path(zip_path)
        _remove_path(model_path)

        if not _download_via_huggingface(repo_id, cache_dir, status_cb, progress_cb, cancel_event):
            raise RuntimeError(
                "Model download failed: both the smch.ir mirror "
                f"({mirror_error}) and the HuggingFace fallback "
                f"({repo_id}) were unable to provide the model."
            ) from mirror_error

        if not model_path.exists():
            raise RuntimeError(
                "Model download failed: the HuggingFace fallback reported "
                f"success for {repo_id!r} but the expected model folder is "
                f"missing: {model_path}"
            ) from mirror_error

        # HuggingFace's own download verifies blob hashes; the smch.ir
        # .md5 manifest describes a different (zip-mirror) layout and
        # would always mismatch here, so skip _verify_extracted_files.
        if status_cb: status_cb("Model ready")
        _notify(progress_cb, phase="ready", status="Model ready", percent=100, detail="Download complete (HuggingFace fallback)")
        return str(model_path)

    if status_cb: status_cb("Model ready")
    _notify(progress_cb, phase="ready", status="Model ready", percent=100, detail="Download complete")
    return str(model_path)
