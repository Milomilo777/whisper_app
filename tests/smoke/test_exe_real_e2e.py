"""Real end-to-end test of the COMPILED exe.

Spawns ``WhisperProject.exe --worker``, sends the actual JSON
``transcribe`` command, and asserts an SRT + JSON land next to the input.
This is the only way to catch PyInstaller packaging bugs (missing data
files, hidden imports). Cf. tests/smoke/README.md for the Session 8
silero_vad_v6.onnx incident that motivated this test.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _ready_or_error(proc: subprocess.Popen[str], deadline_s: float = 180.0) -> None:
    """Drain stdout until a 'ready' event or fail."""
    start = time.time()
    while True:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            raise RuntimeError(f"worker died before ready, rc={proc.poll()}")
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        evt = ev.get("event")
        if evt == "ready":
            return
        if evt == "startup_error":
            raise RuntimeError(f"startup_error: {ev.get('message','')}")
        if time.time() - start > deadline_s:
            raise TimeoutError(f"ready event not seen in {deadline_s}s")


def _drain_until_done(
    proc: subprocess.Popen[str], deadline_s: float = 600.0
) -> tuple[bool, str | None, dict | None]:
    """Drain stdout until 'done' or 'error', returning (done, err, summary)."""
    start = time.time()
    summary = {"language": None, "progress_max": 0}
    while True:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            return False, f"worker died before done, rc={proc.poll()}", summary
        try:
            ev = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        evt = ev.get("event")
        if evt == "done":
            return True, None, summary
        if evt == "error":
            return False, ev.get("message", "worker error"), summary
        if evt == "language_detected":
            summary["language"] = ev.get("language")
        if evt == "progress":
            summary["progress_max"] = max(summary["progress_max"], ev.get("percent", 0))
        if time.time() - start > deadline_s:
            return False, f"transcription did not finish in {deadline_s}s", summary


def test_exe_worker_transcribes_real_video(
    exe_path: Path, model_dir: Path, test_video: Path
) -> None:
    """The compiled exe's worker mode transcribes a real file end-to-end.

    Failure mode this guards against: PyInstaller drops a runtime-loaded
    asset (Silero VAD ONNX, ctranslate2 DLL, tokenizer vocab) and the exe
    crashes when the user hits 'Transcribe'. Source-side tests don't see
    this because they read the asset from site-packages, not the bundle.
    """
    srt = test_video.with_suffix(".srt")
    js = test_video.with_suffix(".json")
    for p in (srt, js):
        if p.exists():
            p.unlink()

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    proc = subprocess.Popen(
        [str(exe_path), "--worker"],
        cwd=str(exe_path.parent),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=creation_flags,
        bufsize=1,
    )

    try:
        _ready_or_error(proc)

        assert proc.stdin is not None
        proc.stdin.write(json.dumps({"action": "transcribe", "file_path": str(test_video)}) + "\n")
        proc.stdin.flush()

        done, err, summary = _drain_until_done(proc)
        assert done, f"transcription failed: {err}  (summary={summary})"

        assert srt.exists() and srt.stat().st_size > 0, f"SRT missing/empty: {srt}"
        assert js.exists() and js.stat().st_size > 0, f"JSON missing/empty: {js}"
        # Spot-check SRT structure
        text = srt.read_text(encoding="utf-8")
        assert "-->" in text, "SRT does not contain timestamp arrows"
        assert summary["progress_max"] >= 90, f"progress capped at {summary['progress_max']}%"
    finally:
        try:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
            proc.stdin.flush()
            proc.wait(timeout=10)
        except Exception:
            proc.terminate()


def test_exe_bundles_silero_vad_asset(exe_path: Path) -> None:
    """Regression for the Session 8 packaging bug.

    The Silero VAD model (``faster_whisper/assets/silero_vad_v6.onnx``)
    must be present alongside the exe. Without it, the worker dies the
    moment VAD-filtered transcription kicks off — which is the default
    setting. The spec collects it via
    ``collect_data_files('faster_whisper')``.
    """
    onnx = exe_path.parent / "faster_whisper" / "assets" / "silero_vad_v6.onnx"
    assert onnx.exists(), f"Silero VAD onnx missing from bundle: {onnx}"
    assert onnx.stat().st_size > 1_000_000, "silero VAD asset suspiciously small"


def test_exe_bundles_ffmpeg(exe_path: Path) -> None:
    """ffmpeg/ffprobe/yt-dlp must sit beside the exe, not under _internal/."""
    bin_dir = exe_path.parent / "bin"
    for name in ("ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe"):
        p = bin_dir / name
        assert p.exists(), f"missing bundled binary: {p}"
