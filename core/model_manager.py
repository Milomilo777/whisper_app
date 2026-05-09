
import hashlib, os, zipfile, requests
from pathlib import Path

def md5_file(path):
    h=hashlib.md5()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def ensure_model(config, status_cb=None):
    model=config["model"]
    model_path=Path(config["model_path"])
    if model_path.exists():
        if status_cb: status_cb("Model already installed")
        return str(model_path)

    zip_url=model["url"]
    md5_url=model["md5"]

    cache_dir=model_path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)

    zip_path=cache_dir / (model["name"] + ".zip")

    if status_cb: status_cb("Downloading model...")
    with requests.get(zip_url, stream=True) as r:
        r.raise_for_status()
        with open(zip_path,"wb") as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)

    if status_cb: status_cb("Verifying MD5...")
    expected=requests.get(md5_url).text.strip().split()[0]
    actual=md5_file(zip_path)

    if expected.lower()!=actual.lower():
        raise RuntimeError(f"MD5 mismatch: {actual} != {expected}")

    if status_cb: status_cb("Extracting model...")
    with zipfile.ZipFile(zip_path,'r') as z:
        z.extractall(cache_dir)

    if not model_path.exists():
        raise RuntimeError(f"Extracted model folder missing: {model_path}")

    if status_cb: status_cb("Model ready")
    return str(model_path)
