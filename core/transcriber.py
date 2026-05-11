from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from faster_whisper import WhisperModel

from .config import load_config
from .model_manager import DownloadCancelled, ensure_model
from .task import TranscriptionTask

logger = logging.getLogger(__name__)

config = load_config()

MODEL=None
MODEL_READY=False
MODEL_ERROR=None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = PROJECT_ROOT / "bin"


def bundled_binary(name: str) -> str:
    exe = f"{name}.exe" if os.name == "nt" else name
    candidate = BIN_DIR / exe
    return str(candidate) if candidate.exists() else name


def log(msg: str, cb: Callable[[str], None] | None = None) -> None:
    if cb:
        cb(msg)
    else:
        logger.info(msg)

def detect_device() -> tuple[str, str]:
    if config.get("device") != "auto":
        return config.get("device", "cpu"), config.get("compute_type", "int8")
    try:
        import ctranslate2
        if ctranslate2.contains_cuda_device():  # type: ignore[attr-defined]
            supported = set(ctranslate2.get_supported_compute_types("cuda"))
            for ct in ("float16", "int8_float16", "int8"):
                if ct in supported:
                    return "cuda", ct
    except (ImportError, AttributeError, RuntimeError):
        pass
    try:
        import torch  # type: ignore[import-not-found]
        if torch.cuda.is_available():
            return "cuda", "float16"
    except (ImportError, AttributeError):
        pass
    return "cpu", config.get("compute_type", "int8")

device,compute_type=detect_device()

def is_model_ready() -> bool:
    return MODEL_READY

def get_model_error() -> str | None:
    return MODEL_ERROR

def load_existing_model(status_cb: Callable[[str], None] | None = None) -> bool:
    global MODEL, MODEL_READY, MODEL_ERROR
    MODEL_READY=False
    MODEL_ERROR=None
    model_path=Path(config["model_path"])

    if not model_path.exists():
        MODEL_ERROR=f"Model folder missing: {model_path}"
        if status_cb: status_cb(MODEL_ERROR)
        return False

    try:
        if status_cb: status_cb("Loading existing Whisper model...")
        MODEL=WhisperModel(str(model_path),device=device,compute_type=compute_type)
        MODEL_READY=True
        if status_cb: status_cb("Model loaded")
        return True
    except Exception as e:
        MODEL_ERROR=str(e)
        if status_cb: status_cb(f"Existing model failed to load: {e}")
        return False

def load_model(
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    global MODEL, MODEL_READY, MODEL_ERROR
    MODEL_READY=False
    MODEL_ERROR=None
    try:
        model_path=ensure_model(config, status_cb, progress_cb, cancel_event)
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Model download cancelled")
        if status_cb: status_cb("Loading Whisper model...")
        if progress_cb:
            progress_cb({"phase":"load","status":"Loading Whisper model...","percent":100,"detail":"Preparing model for transcription"})
        MODEL=WhisperModel(model_path,device=device,compute_type=compute_type)
        MODEL_READY=True
        if status_cb: status_cb("Model loaded")
        if progress_cb:
            progress_cb({"phase":"loaded","status":"Model loaded","percent":100,"detail":"Ready"})
        return True
    except DownloadCancelled as e:
        MODEL_ERROR=None
        if status_cb: status_cb(str(e))
        return False
    except Exception as e:
        MODEL_ERROR=str(e)
        if status_cb: status_cb(f"ERROR: {e}")
        raise

def load_model_async(
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    try:
        load_model(status_cb, progress_cb, cancel_event)
    except Exception:
        pass

def start_background_model_load(status_cb: Callable[[str], None] | None = None) -> None:
    threading.Thread(target=load_model_async,args=(status_cb,),daemon=True).start()

def get_duration(path: str) -> float:
    ffprobe = bundled_binary("ffprobe")
    r=subprocess.run(
        [ffprobe,"-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(
            f"ffprobe failed (exit={r.returncode}) for {path}: {r.stderr.strip() or 'no output'}"
        )
    return float(r.stdout.strip())

def fmt(sec: float) -> str:
    h=int(sec//3600);m=int((sec%3600)//60);s=int(sec%60)
    return f"{h:02}:{m:02}:{s:02}"

def transcribe(
    task: TranscriptionTask,
    progress_cb: Callable[[int], None] | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> None:
    global MODEL
    while not MODEL_READY:
        if MODEL_ERROR:
            raise RuntimeError(MODEL_ERROR)
        time.sleep(0.5)

    duration=get_duration(task.file_path)
    start=time.time()
    log(f"Processing: {task.file_path}",log_cb)

    assert MODEL is not None  # MODEL_READY guarantees this
    segments,_=MODEL.transcribe(task.file_path)
    base=os.path.splitext(task.file_path)[0]

    srt=[];data=[]
    for i,seg in enumerate(segments,1):
        if task.cancelled:
            log("Task cancelled",log_cb)
            return

        while task.paused and not task.cancelled:
            time.sleep(0.2)

        percent=min(100,int((seg.end/duration)*100))
        msg=f"[{percent}%] {fmt(seg.start)} --> {fmt(seg.end)} | {seg.text.strip()}"
        log(msg,log_cb)

        if progress_cb:
            progress_cb(percent)

        srt.append(f"{i}\n{fmt(seg.start)} --> {fmt(seg.end)}\n{seg.text.strip()}\n")
        data.append({"start":seg.start,"end":seg.end,"text":seg.text.strip()})

    with open(base+".srt","w",encoding="utf-8") as f:
        f.write("\n".join(srt))

    with open(base+".json","w",encoding="utf-8") as f:
        json.dump(data,f,indent=2)

    if progress_cb:
        progress_cb(100)

    elapsed=time.time()-start
    log(f"Done in {elapsed:.2f}s",log_cb)
