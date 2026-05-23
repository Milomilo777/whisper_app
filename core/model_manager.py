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
import os
import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import requests


# Hard cap on MD5-mismatch retries. A permanently-broken CDN or
# manifest mistake would otherwise put ``ensure_model`` in a
# bandwidth-eating infinite redownload loop (audit P1-4).
_DEFAULT_MAX_DOWNLOAD_RETRIES = 3


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


# Content-Type values we accept as "this is a real binary download".
# Some CDNs return text/html (an error page) with a 200, and the old
# code would write that HTML to disk and then fail at unzip time —
# wasting bandwidth and confusing the user (audit P1-3).
_ACCEPTABLE_ZIP_CONTENT_TYPES: tuple[str, ...] = (
    "application/zip",
    "application/octet-stream",
    "application/x-zip",
    "application/x-zip-compressed",
    "binary/octet-stream",
)

# First 4 bytes of every zip archive (local file header).
_ZIP_MAGIC = b"PK\x03\x04"


def _require_https(url: str, *, label: str) -> None:
    """Reject ``http://`` URLs outright before any network call (P1-20).

    A hand-edited config can downgrade to plain HTTP; the entire 3 GB
    zip would then download with no TLS, and the MD5 manifest fetched
    from the same downgrade-vulnerable origin offers zero MITM
    protection.
    """
    if not url:
        raise RuntimeError(f"{label} is empty")
    scheme = urlparse(url).scheme.lower()
    if scheme != "https":
        raise RuntimeError(
            f"{label} must be https:// (got {scheme!r}: {url})"
        )


def _download_zip(
    zip_url: str,
    zip_path: Path,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """HTTP GET with byte-range resume + UI-friendly progress events.

    On a 416 from the server (range outside file size) we assume the
    file is already fully downloaded and return the existing path.

    When we asked for a Range but the server replied with a plain 200
    (no Range support), we reset and start over in ``wb`` mode — the
    file handle is opened AFTER the branch so the new full body
    overwrites the partial rather than appending to it (audit P0-4).

    Refuses non-HTTPS URLs (P1-20) and validates the response
    Content-Type before writing anything to disk (P1-3).
    """
    _require_https(zip_url, label="model download URL")

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
            # Server ignored our Range header. Discard the partial
            # and start fresh — the file open below now sees the
            # reset values.
            existing = 0
            downloaded = 0
            mode = "wb"

        # Reject non-binary content (HTML error pages served as 200).
        content_type = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type and not any(
            content_type == ct or content_type.startswith(ct + ";")
            for ct in _ACCEPTABLE_ZIP_CONTENT_TYPES
        ):
            raise RuntimeError(
                f"Download server returned non-zip content "
                f"(Content-Type: {content_type!r}). The mirror is likely "
                "serving an error page. Try again later."
            )

        content_length = int(r.headers.get("content-length") or 0)
        total = existing + content_length if content_length else 0

        first_chunk = True
        # Open AFTER the 200-vs-206 branch (P0-4) so ``mode`` is
        # always the post-reset value.
        with open(zip_path, mode) as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if cancel_event and cancel_event.is_set():
                    raise DownloadCancelled("Model download cancelled")
                if not chunk:
                    continue
                if first_chunk and mode == "wb":
                    # Sniff the magic bytes — if the server sent us
                    # an HTML body with a missing/wrong Content-Type
                    # the first chunk will not start with ``PK\x03\x04``.
                    if not chunk.startswith(_ZIP_MAGIC):
                        # Look at the first 64 bytes for the user
                        # error message; HTML usually starts with
                        # ``<!DOCTYPE`` or ``<html``.
                        preview = chunk[:64].decode("utf-8", errors="replace")
                        raise RuntimeError(
                            "Download server returned non-zip content "
                            f"(first bytes: {preview!r}). The mirror is "
                            "likely serving an error page. Try again later."
                        )
                first_chunk = False
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


def _path_contains_traversal(rel: str) -> bool:
    """Return True if ``rel`` is an absolute path or has ``..`` segments.

    Used by both the MD5-manifest verifier (P1-1) and the zip
    extractor (P1-2). Catches all three traversal flavours:

    * ``../../escape.txt``
    * ``C:/Windows/x``
    * ``\\\\server\\share\\x``
    """
    if not rel:
        return True
    # Cheap absolute-path tests before any normalisation.
    if rel.startswith(("/", "\\")):
        return True
    # Windows drive letter (``C:`` or ``c:``).
    if len(rel) >= 2 and rel[1] == ":":
        return True
    # Reject ``..`` as a segment in EITHER separator.
    for sep in ("/", "\\"):
        parts = rel.split(sep)
        if ".." in parts:
            return True
    return False


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """Validate each ZipInfo entry before extracting (audit P1-2).

    Python's ``ZipFile.extractall`` only sanitises names since 3.12
    and even then doesn't refuse symlinks. We do a manual pass:

    * Refuse entries with absolute paths or ``..`` segments.
    * Refuse entries that resolve outside ``dest_dir`` on the host FS.
    * Refuse symlink entries entirely (no model file in our archive
      is or should be a symlink — accepting them lets a hostile CDN
      plant a symlink that the verifier then chases).
    """
    dest_real = dest_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            name = info.filename
            if not name:
                continue
            if _path_contains_traversal(name):
                raise RuntimeError(
                    f"Refusing to extract zip member with unsafe path: "
                    f"{name!r}"
                )
            # Symlinks in zip have mode bits set on external_attr.
            # External-attr high 16 bits = Unix mode; 0o120000 = symlink.
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if (unix_mode & 0o170000) == 0o120000:
                raise RuntimeError(
                    f"Refusing to extract symlink zip member: {name!r}"
                )
            # Compute the destination and verify it sits under
            # dest_dir on the real filesystem.
            target = (dest_dir / name).resolve()
            try:
                target.relative_to(dest_real)
            except ValueError:
                raise RuntimeError(
                    f"Refusing to extract zip member outside cache: "
                    f"{name!r} → {target}"
                )
        # Validation pass complete — actually extract.
        z.extractall(dest_dir)


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

    Rejects manifest entries with absolute paths or ``..`` segments
    BEFORE resolving (P1-1), and refuses to follow symlinks during
    verification — an attacker-planted symlink could let a malicious
    manifest read files outside the cache (information disclosure
    via timing).
    """
    _require_https(md5_url, label="MD5 manifest URL")

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

        # FIRST refuse traversal patterns on the unresolved string —
        # before resolve() gets to chase any planted symlink.
        if _path_contains_traversal(relative_path):
            raise RuntimeError(
                f"Unsafe MD5 manifest path: {relative_path}"
            )

        file_path = cache_dir / relative_path
        # Refuse symlinks at the file path AND at any parent in the
        # path. ``Path.is_symlink`` only checks the leaf; we walk
        # upwards manually so a symlinked intermediate directory
        # doesn't slip through.
        check = file_path
        while True:
            try:
                if check.is_symlink():
                    raise RuntimeError(
                        f"Refusing to verify across symlink: {check}"
                    )
            except OSError:
                pass
            if check == cache_dir or check.parent == check:
                break
            check = check.parent

        resolved = file_path.resolve()
        try:
            resolved.relative_to(cache_root)
        except ValueError:
            raise RuntimeError(
                f"Unsafe MD5 manifest path resolves outside cache: "
                f"{relative_path}"
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
    *,
    max_retries: int = _DEFAULT_MAX_DOWNLOAD_RETRIES,
) -> str:
    """Idempotent: download + extract + MD5-verify the model.

    Returns the absolute path of the model folder. Safe to call on
    every startup — when the model is already on disk and passes MD5,
    this is a quick checksum-only pass.

    MD5 mismatches trigger a full restart: zip + folder both wiped,
    download from byte 0. Capped at ``max_retries`` attempts so a
    permanently-broken CDN doesn't eat unbounded bandwidth (P1-4).

    Both the model URL and the MD5 manifest URL must be https://
    (P1-20) — non-TLS downloads are rejected before any network I/O.
    """
    model = config["model"]
    model_path = Path(config["model_path"])
    zip_url = model["url"]
    md5_url = model["md5"]

    _require_https(zip_url, label="model download URL")
    _require_https(md5_url, label="MD5 manifest URL")

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

    last_mismatches: list[tuple[str, str, str]] = []
    for attempt in range(1, max_retries + 1):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Model download cancelled")

        if status_cb:
            status_cb(
                f"Downloading model... (attempt {attempt}/{max_retries})"
            )
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
        _safe_extract_zip(zip_path, cache_dir)

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
        last_mismatches = mismatches

        if attempt < max_retries:
            if status_cb:
                status_cb(
                    f"MD5 mismatch (attempt {attempt}/{max_retries}). "
                    "Deleting archive + folder; restarting download."
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
    else:  # for-else runs when the loop exhausted max_retries without break
        files = ", ".join(rel for rel, _, _ in last_mismatches[:5])
        if len(last_mismatches) > 5:
            files += f", ... ({len(last_mismatches) - 5} more)"
        raise RuntimeError(
            f"Model download failed: MD5 mismatch persisted across "
            f"{max_retries} attempts. The CDN may be serving corrupt "
            f"data. Failing files: {files}"
        )

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
    raw = (config.get("model_path") or "").strip()
    if not raw:
        return False
    p = Path(raw)
    return p.exists() and p.is_dir()
