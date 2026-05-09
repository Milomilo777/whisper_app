
import hashlib, shutil, time, zipfile, requests
from pathlib import Path
from urllib.parse import unquote, urlparse

class DownloadCancelled(RuntimeError):
    pass

def md5_file(path, cancel_event=None):
    h=hashlib.md5()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Model download cancelled")
            h.update(chunk)
    return h.hexdigest()

def _remove_path(path):
    path=Path(path)
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

def _fmt_bytes(value):
    value=float(value or 0)
    for unit in ("B","KB","MB","GB","TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value/=1024

def _fmt_time(seconds):
    if seconds is None:
        return "--:--"
    seconds=max(0,int(seconds))
    h=seconds//3600
    m=(seconds%3600)//60
    s=seconds%60
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"

def _notify(progress_cb, **payload):
    if progress_cb:
        progress_cb(payload)

def _zip_name_from_url(zip_url):
    name=Path(unquote(urlparse(zip_url).path)).name
    return name or "model.zip"

def _parse_md5_manifest(text):
    entries=[]
    for line in text.splitlines():
        line=line.strip()
        if not line:
            continue

        parts=line.split(None,1)
        if len(parts)!=2:
            continue

        checksum,path=parts
        path=path.lstrip("*").replace("\\","/")
        if path.startswith("./"):
            path=path[2:]
        entries.append((checksum.lower(),path))
    return entries

def _download_zip(zip_url, zip_path, progress_cb=None, cancel_event=None):
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

def _verify_extracted_files(cache_dir, md5_url, status_cb=None, progress_cb=None, cancel_event=None):
    response=requests.get(md5_url, timeout=(10, 30))
    response.raise_for_status()
    entries=_parse_md5_manifest(response.text)
    if not entries:
        raise RuntimeError("MD5 manifest does not contain any files")

    cache_root=cache_dir.resolve()
    mismatches=[]

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

def ensure_model(config, status_cb=None, progress_cb=None, cancel_event=None):
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

    while True:
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
            z.extractall(cache_dir)

        if not model_path.exists():
            raise RuntimeError(f"Extracted model folder missing: {model_path}")

        if status_cb: status_cb("Verifying extracted model files...")
        mismatches=_verify_extracted_files(cache_dir, md5_url, status_cb, progress_cb, cancel_event)
        if not mismatches:
            _remove_path(zip_path)
            break

        if status_cb:
            status_cb("MD5 mismatch. Deleting model archive and folder, then restarting from zero...")

        _notify(
            progress_cb,
            phase="restart",
            status="MD5 mismatch. Restarting download from zero...",
            percent=0,
            detail=f"{len(mismatches)} file checksum(s) failed",
        )
        _remove_path(zip_path)
        _remove_path(model_path)

    if status_cb: status_cb("Model ready")
    _notify(progress_cb, phase="ready", status="Model ready", percent=100, detail="Download complete")
    return str(model_path)
