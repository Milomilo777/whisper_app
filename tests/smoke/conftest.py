"""Shared fixtures + skip-guards for the smoke suite.

Smoke tests need real local resources (the Whisper model, a video file,
optionally the compiled exe). On any machine missing those, the test
politely skips instead of failing — so the unit suite can still run
hermetically.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_VIDEO = Path(r"E:\3029-NWN-Daily-Scroll-2m_0002.mp4")
DEFAULT_MODEL_PARENT = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    / "WhisperProject" / "Cache" / "models"
)
DEFAULT_MODEL_DIR = DEFAULT_MODEL_PARENT / "models--Systran--faster-whisper-large-v3"
DEFAULT_EXE = REPO_ROOT / "dist" / "WhisperProject" / "WhisperProject.exe"


@pytest.fixture(scope="session")
def test_video() -> Path:
    """Path to a real audio/video file. Override via $WHISPER_SMOKE_VIDEO."""
    p = Path(os.environ.get("WHISPER_SMOKE_VIDEO", str(DEFAULT_VIDEO)))
    if not p.exists():
        pytest.skip(f"test video not present: {p}")
    return p


@pytest.fixture(scope="session")
def model_dir() -> Path:
    """Local faster-whisper model folder."""
    p = Path(os.environ.get("WHISPER_SMOKE_MODEL", str(DEFAULT_MODEL_DIR)))
    if not p.exists() or not (p / "model.bin").exists():
        pytest.skip(f"local model not present: {p}")
    return p


@pytest.fixture(scope="session")
def exe_path() -> Path:
    """Compiled WhisperProject.exe (one-dir build)."""
    p = Path(os.environ.get("WHISPER_SMOKE_EXE", str(DEFAULT_EXE)))
    if not p.exists():
        pytest.skip(f"compiled exe not present: {p}  (run build.bat)")
    return p


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT
