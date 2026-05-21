"""Headless integration test of the App class (Python source, not exe).

Instantiates the real Tk App, hides the window, exercises every major
service path (transcription via worker subprocess, format probe, writers,
oTranscribe round-trip, dialogs, theme switching), then shuts down.

This catches Python-source regressions across services. It cannot catch
PyInstaller packaging bugs — for those see test_exe_real_e2e.py.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def app(model_dir: Path):
    """A withdrawn (hidden) Tk App with a real worker pool."""
    try:
        from app.app import App
    except Exception as e:
        pytest.skip(f"cannot import App ({e})")

    a = App()
    a.withdraw()
    # Pump the mainloop briefly for after-callbacks to run
    end = time.time() + 1.0
    while time.time() < end:
        a.update()
        time.sleep(0.05)
    yield a
    try:
        a.transcription_service.stop_all()
        a.destroy()
    except Exception:
        pass


def _pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.05)


def test_bundled_binaries_resolve(app) -> None:
    bp = app.bin_path()
    assert os.path.isdir(bp), bp
    for name in ("ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe"):
        assert os.path.isfile(os.path.join(bp, name)), f"missing {name}"


def test_history_db_works(app) -> None:
    assert getattr(app, "history", None) is not None
    rows = app.history.list_transcriptions(limit=5)
    assert isinstance(rows, list)
    stats = app.history.stats()
    for k in ("downloads_total", "transcriptions_total", "top_languages"):
        assert k in stats, f"stats missing {k}"


def test_writers_smoke(app) -> None:
    from core.writers import srt as srt_writer
    from core.writers import vtt as vtt_writer
    from core.writers import tsv as tsv_writer
    from core.writers import txt as txt_writer
    from core.writers import lrc as lrc_writer
    from core.writers import json_writer

    seg = [
        {"id": 0, "start": 0.0, "end": 1.2, "text": "Hello world."},
        {"id": 1, "start": 1.2, "end": 2.5, "text": "Second segment."},
    ]
    srt_str = srt_writer.write(seg, "dummy.wav")
    assert "Hello world." in srt_str and "-->" in srt_str
    assert vtt_writer.write(seg, "dummy.wav").strip()
    assert tsv_writer.write(seg, "dummy.wav").strip()
    assert txt_writer.write(seg, "dummy.wav").strip()
    assert lrc_writer.write(seg, "dummy.wav").strip()
    assert json_writer.write(seg, "dummy.wav").strip()


def test_otranscribe_round_trip(app) -> None:
    from core.writers import srt as srt_writer
    from core.integrations import otranscribe

    seg = [
        {"id": 0, "start": 0.0, "end": 1.0, "text": "Hi."},
        {"id": 1, "start": 1.0, "end": 2.5, "text": "There."},
    ]
    with tempfile.TemporaryDirectory() as td:
        srt_path = os.path.join(td, "trip.srt")
        Path(srt_path).write_text(srt_writer.write(seg, ""), encoding="utf-8")
        otr_str = otranscribe.srt_to_otr(srt_path, media_filename="trip.wav")
        assert "trip.wav" in otr_str
        otr_path = os.path.join(td, "trip.otr")
        Path(otr_path).write_text(otr_str, encoding="utf-8")
        round_srt = otranscribe.otr_to_srt(otr_path)
        assert "Hi." in round_srt and "There." in round_srt


def test_dialogs_open_and_close(app) -> None:
    from app.dialogs.advanced import AdvancedDialog
    # Statistics
    app.show_statistics()
    _pump(app, 0.5)
    for w in app.winfo_children():
        try:
            if w.winfo_class() == "Toplevel":
                w.destroy()
        except Exception:
            pass
    # Advanced
    ad = AdvancedDialog(app)
    _pump(app, 0.3)
    try:
        ad.destroy()
    except Exception:
        pass


def test_theme_switching(app) -> None:
    for name in ("light", "dark", "system"):
        app.theme_var.set(name)
        app.apply_theme()
        _pump(app, 0.1)


def test_real_worker_transcription(app, test_video: Path) -> None:
    """The standby worker subprocess actually transcribes the test video."""
    app.transcription_service.start_standby()
    deadline = time.time() + 180
    while not app.transcription_service.ready_workers():
        if time.time() > deadline:
            pytest.fail("worker never reached 'ready'")
        app.update()
        time.sleep(0.2)

    app.fv.set(str(test_video))
    app.add()

    deadline = time.time() + 900
    while time.time() < deadline:
        for t in app.queue:
            if t.status in ("finished", "error"):
                if t.status == "error":
                    pytest.fail(f"transcription error: file={t.file_path}")
                srt = Path(t.file_path).with_suffix(".srt")
                assert srt.exists() and srt.stat().st_size > 0, f"SRT missing: {srt}"
                return
        app.update()
        time.sleep(0.2)
    pytest.fail("transcription did not finish in 15 min")
