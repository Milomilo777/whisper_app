r"""Regression tests for the frontend-edge backlog cluster (appui).

Each test pins a fix made in ``app/app.py``; all are hermetic — no Tk root,
no network, no model. UI methods are exercised as unbound functions on a bare
``App.__new__(App)`` object with only the attributes the method touches stubbed
(the App.__new__ + stubbed-attrs pattern from test_fixpack_frontend_edges.py).

Covered:
  (a) Re-run / Resume dedup — a finished row re-run twice (or re-run while a
      prior re-run of the same file is still pending) must NOT enqueue a second
      concurrent transcription of the same file.
  (c) _start_server_async clamps an out-of-range typed port (0 / >65535) to the
      default before binding, mirroring _save_server_prefs.
  (g) _on_server_started gives a DISTINCT status when LAN sharing was requested
      but the network address couldn't be detected (no misleading
      "Running on this computer.").
  (d/e/f) _on_drop logs a clear message for a no-op drop (folder / dead path),
      for a multi-URL drop (only the first used), recognises file:// URIs, and
      flags unsupported schemes (ftp:/magnet:/smb:) instead of swallowing them.
  _file_uri_to_path conversion.
"""
from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def App():
    if "faster_whisper" not in sys.modules:
        fw = types.ModuleType("faster_whisper")
        fw.WhisperModel = object  # type: ignore[attr-defined]
        sys.modules["faster_whisper"] = fw
    from app.app import App as _App
    return _App


class _Svc:
    def ensure_worker_ready(self, app):  # noqa: ARG002
        return True


def _bare_app(App):
    a = App.__new__(App)
    a.queue = []
    a.transcription_service = _Svc()
    a.refresh = lambda *x, **k: None
    a.logs = []
    a.log = a.logs.append
    return a


def _task(file="movie.wav", status="finished"):
    from core.task import TranscriptionTask
    t = TranscriptionTask(file)
    t.status = status
    return t


# --- (a) Re-run / Resume dedup ----------------------------------------------

def test_rerun_blocked_when_same_file_still_pending(App):
    a = _bare_app(App)
    # A non-terminal task for the same file is already queued.
    a.queue.append(_task("movie.wav", status="waiting"))
    App._rerun_task(a, _task("movie.wav", status="finished"))
    # No second concurrent task was enqueued.
    assert len(a.queue) == 1
    assert any("already in the queue" in m for m in a.logs)


def test_rerun_allowed_when_only_terminal_dups(App):
    a = _bare_app(App)
    # Prior runs of the same file are all terminal — a fresh re-run is fine.
    a.queue.append(_task("movie.wav", status="finished"))
    App._rerun_task(a, _task("movie.wav", status="finished"))
    assert len(a.queue) == 2


def test_resume_blocked_when_same_file_running(App):
    a = _bare_app(App)
    a.queue.append(_task("clip.wav", status="running"))
    App.resume_task(a, _task("clip.wav", status="cancelled"))
    assert len(a.queue) == 1
    assert any("already in the queue" in m for m in a.logs)


def test_bulk_rerun_skips_pending_dup_only(App):
    a = _bare_app(App)
    a.queue.append(_task("a.wav", status="running"))   # blocks a.wav
    App._bulk_rerun(a, [_task("a.wav"), _task("b.wav")])
    # a.wav skipped, b.wav enqueued.
    files = [t.file_path for t in a.queue]
    assert files.count("a.wav") == 1 and "b.wav" in files


def test_bulk_resume_skips_pending_dup_only(App):
    a = _bare_app(App)
    a.queue.append(_task("a.wav", status="paused"))
    App._bulk_resume(a, [_task("a.wav"), _task("b.wav")])
    files = [t.file_path for t in a.queue]
    assert files.count("a.wav") == 1 and "b.wav" in files


def test_rerun_of_distinct_file_not_blocked(App):
    a = _bare_app(App)
    a.queue.append(_task("other.wav", status="running"))
    App._rerun_task(a, _task("movie.wav", status="finished"))
    assert len(a.queue) == 2


# --- (c) server port clamp ---------------------------------------------------

class _Var:
    def __init__(self, v):
        self._v = v

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class _Btn:
    def config(self, **k):  # noqa: ARG002
        pass


def _make_fake_core_server(recorder):
    mod = types.ModuleType("core.server")
    mod.HOST_LAN = "0.0.0.0"
    mod.HOST_LOOPBACK = "127.0.0.1"

    class _Handle:
        def __init__(self):
            self.port = 0

        def start(self, host, port, token, *, max_upload_mb=512):  # noqa: ARG002
            recorder["host"] = host
            recorder["port"] = port
            # Mimic auto_port: an in-range port binds verbatim.
            self.port = port

        def urls(self):
            if recorder["host"] == "0.0.0.0":
                # Simulate the share-LAN case with LAN-IP detection available.
                return [f"http://127.0.0.1:{self.port}/",
                        f"http://192.168.1.5:{self.port}/"]
            return [f"http://127.0.0.1:{self.port}/"]

    mod.ServerHandle = _Handle
    return mod


def _server_app(App, typed_port):
    a = App.__new__(App)
    a.app_config = {}
    a.server_port_var = _Var(typed_port)
    a.server_share_lan_var = _Var(False)
    a.server_token_var = _Var("")
    a.server_toggle_btn = _Btn()
    a.server_status_var = _Var("")
    a.server_url_var = _Var("")
    a._server_busy = False
    a.post_to_main = lambda fn: fn()
    a._on_server_started = lambda *x: None
    a._on_server_failed = lambda *x: None
    return a


def _run_start_sync(App, monkeypatch, a):
    """Drive _start_server_async with the worker thread running inline."""
    import threading as real_threading

    class _SyncThread:
        def __init__(self, target=None, name=None, daemon=None):  # noqa: ARG002
            self._target = target

        def start(self):
            if self._target is not None:
                self._target()

    monkeypatch.setattr(real_threading, "Thread", _SyncThread)
    App._start_server_async(a)


def test_start_server_clamps_overflow_port(App, monkeypatch):
    rec: dict = {}
    monkeypatch.setitem(sys.modules, "core.server",
                        _make_fake_core_server(rec))
    a = _server_app(App, typed_port=99999)
    _run_start_sync(App, monkeypatch, a)
    # 99999 is out of range -> clamped to the 8765 default, not passed raw.
    assert rec["port"] == 8765


def test_start_server_clamps_zero_port(App, monkeypatch):
    rec: dict = {}
    monkeypatch.setitem(sys.modules, "core.server",
                        _make_fake_core_server(rec))
    a = _server_app(App, typed_port=0)
    _run_start_sync(App, monkeypatch, a)
    assert rec["port"] == 8765


def test_start_server_keeps_valid_port(App, monkeypatch):
    rec: dict = {}
    monkeypatch.setitem(sys.modules, "core.server",
                        _make_fake_core_server(rec))
    a = _server_app(App, typed_port=8080)
    _run_start_sync(App, monkeypatch, a)
    assert rec["port"] == 8080


# --- (g) LAN-detection-failed status ----------------------------------------

def _started_app(App):
    a = App.__new__(App)
    a.app_config = {}
    a.server_port_var = _Var(8765)
    a.server_toggle_btn = _Btn()
    a.server_open_btn = _Btn()
    a.server_status_var = _Var("")
    a.server_url_var = _Var("")
    a._server_busy = True
    a.logs = []
    a.log = a.logs.append
    return a


def test_lan_share_with_failed_ip_gives_distinct_status(App):
    a = _started_app(App)
    # share_lan requested, but reachable_urls returned only the loopback URL
    # (LAN-IP detection failed) -> single-element urls list.
    App._on_server_started(a, ["http://127.0.0.1:8765/"], 8765, True)
    status = a.server_status_var.get()
    assert "couldn't be detected" in status
    assert status != "Running on this computer."


def test_lan_share_with_ip_reports_network(App):
    a = _started_app(App)
    App._on_server_started(
        a, ["http://127.0.0.1:8765/", "http://192.168.1.5:8765/"], 8765, True)
    assert "your network" in a.server_status_var.get()


def test_loopback_only_reports_local(App):
    a = _started_app(App)
    App._on_server_started(a, ["http://127.0.0.1:8765/"], 8765, False)
    assert a.server_status_var.get() == "Running on this computer."


# --- (d/e/f) drop edges ------------------------------------------------------

class _Nb:
    def __init__(self):
        self.selected = None

    def select(self, tab):
        self.selected = tab


def _drop_app(App):
    a = App.__new__(App)
    a.fv = _Var("")
    a.download_url_var = _Var("")
    a.nb = _Nb()
    a.t1 = "transcribe"
    a.t3 = "download"
    a.logs = []
    a.log = a.logs.append
    a.enqueued = []

    def _bulk(paths):
        a.enqueued.extend(paths)
        return len(paths)

    a._bulk_enqueue = _bulk
    return a


def test_drop_folder_or_dead_path_logs_no_op(App, monkeypatch):
    monkeypatch.setattr("app.app.os.path.isfile", lambda s: False)
    a = _drop_app(App)
    App._on_drop(a, types.SimpleNamespace(data=r"C:\some\folder"))
    assert any("Nothing to do" in m for m in a.logs)


def test_drop_multi_url_notes_only_first_used(App, monkeypatch):
    monkeypatch.setattr("app.app.os.path.isfile", lambda s: False)
    a = _drop_app(App)
    App._on_drop(a, types.SimpleNamespace(
        data="https://a.example/v1 https://b.example/v2"))
    assert a.download_url_var.get() == "https://a.example/v1"
    assert any("Only the first" in m for m in a.logs)


def test_drop_unsupported_scheme_flagged(App, monkeypatch):
    monkeypatch.setattr("app.app.os.path.isfile", lambda s: False)
    a = _drop_app(App)
    App._on_drop(a, types.SimpleNamespace(data="ftp://host/clip.mp4"))
    assert any("unsupported type" in m for m in a.logs)
    # Nothing was enqueued or routed.
    assert a.enqueued == [] and a.download_url_var.get() == ""


def test_drop_magnet_scheme_flagged(App, monkeypatch):
    monkeypatch.setattr("app.app.os.path.isfile", lambda s: False)
    a = _drop_app(App)
    App._on_drop(a, types.SimpleNamespace(data="magnet:?xt=urn:btih:abc"))
    assert any("unsupported type" in m for m in a.logs)


def test_drop_file_uri_resolves_to_local_path(App, monkeypatch):
    real = r"C:\videos\clip.mp4"
    monkeypatch.setattr("app.app.os.path.isfile", lambda s: s == real)
    a = _drop_app(App)
    App._on_drop(a, types.SimpleNamespace(data="file:///C:/videos/clip.mp4"))
    # Resolved + treated as a single dropped file (lands in the file field).
    assert a.fv.get() == real
    assert a.nb.selected == a.t1


# --- _file_uri_to_path -------------------------------------------------------

def test_file_uri_to_path_windows():
    from app.app import _file_uri_to_path
    assert _file_uri_to_path("file:///C:/videos/my%20clip.mp4") == \
        r"C:\videos\my clip.mp4"


def test_file_uri_to_path_non_file_uri_returns_empty():
    from app.app import _file_uri_to_path
    assert _file_uri_to_path("ftp://host/x") == ""
    assert _file_uri_to_path(r"C:\plain\path.mp4") == ""
