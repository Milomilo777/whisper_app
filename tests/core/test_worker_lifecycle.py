"""Tests for model-load + dispatch lifecycle (P0-2/5/7).

Most of this can be verified without spinning a real worker
process — the relevant bits are pure-Python helpers.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from core import config as _cfg
from core import worker as _w


# ---------------------------------------------------------------- P0-2

def test_heartbeat_starts_before_model_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """Heartbeat thread must be spawned BEFORE load_existing_model.

    The bug-fix is structural: in worker.main(), _start_heartbeat()
    is now called above load_existing_model(). We assert via a
    monkeypatch that records call order.
    """
    order: list[str] = []

    def fake_start_heartbeat() -> None:
        order.append("heartbeat")

    def fake_load(cb: Any = None) -> bool:
        order.append("load")
        return False  # short-circuit so main exits quickly

    def fake_emit(event: str, **kw: Any) -> None:
        order.append(f"emit:{event}")

    def fake_reconfigure() -> None:
        pass

    def fake_setup_logging(_lvl: str = "INFO") -> None:
        pass

    monkeypatch.setattr(_w, "_start_heartbeat", fake_start_heartbeat)
    monkeypatch.setattr(_w, "load_existing_model", fake_load)
    monkeypatch.setattr(_w, "emit", fake_emit)
    monkeypatch.setattr(_w, "_reconfigure_stdio_utf8", fake_reconfigure)
    monkeypatch.setattr(_w, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(_w, "get_model_error", lambda: "fake error")

    rc = _w.main()
    assert rc == 1  # load failed → startup_error → rc 1

    # heartbeat MUST come before load.
    hb_idx = order.index("heartbeat")
    load_idx = order.index("load")
    assert hb_idx < load_idx, f"heartbeat must start before load; got {order}"


def test_heartbeat_emits_while_load_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """A slow load (mocked sleep) sees at least one heartbeat tick."""
    # Reduce heartbeat interval so the test is fast.
    monkeypatch.setattr(_w, "HEARTBEAT_INTERVAL_SECONDS", 0.05)

    ticks: list[float] = []
    real_emit = _w.emit

    def recording_emit(event: str, **kw: Any) -> None:
        if event == "heartbeat":
            ticks.append(time.time())

    monkeypatch.setattr(_w, "emit", recording_emit)

    # Spawn the heartbeat the same way the worker does.
    _w._start_heartbeat()

    # Simulate a slow load.
    time.sleep(0.3)

    assert len(ticks) >= 2, (
        f"expected ≥2 heartbeats during the simulated slow load; got {len(ticks)}"
    )

    # Restore emit (the heartbeat daemon still runs but only at our
    # recording function; that's fine — daemon dies with the test
    # process).
    monkeypatch.setattr(_w, "emit", real_emit)


# ---------------------------------------------------------------- P0-5

def test_double_transcribe_click_is_serialised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A re-entrant _on_transcribe_click is a no-op while the first
    call is still running its blocking dialog wait (P0-5)."""
    from app import app as _aapp

    class _FakeVar:
        def __init__(self, v: str) -> None:
            self.v = v

        def set(self, v: str) -> None:
            self.v = v

        def get(self) -> str:
            return self.v

    class _FakeBtn:
        def configure(self, **_kw: Any) -> None:
            pass

    class _FakeTask:
        status = "waiting"
        cancelled = False

    class _Stub:
        def __init__(self) -> None:
            self.queue: list[Any] = [_FakeTask()]
            self.status_var = _FakeVar("")
            self.dispatched = 0
            self.transcribe_btn = _FakeBtn()
            self.worker: dict[str, Any] | None = {
                "process": object(), "ready": True, "task": None,
            }
            self.config_dict: dict[str, Any] = {"model_path": "/tmp/m"}

        def _dispatch_next(self) -> None:
            self.dispatched += 1

        def _worker_alive(self) -> bool:
            return True

        def _spawn_worker_blocking(self) -> bool:
            return True

    # is_model_on_disk → True so we skip the download dialog path.
    monkeypatch.setattr(_aapp, "is_model_on_disk", lambda _c: True)
    monkeypatch.setattr(_aapp, "load_config", lambda: {"model_path": "/tmp/m"})

    stub = _Stub()
    click = _aapp.App._on_transcribe_click.__get__(stub, _Stub)

    # Re-enter dispatch mid-call to simulate a double-click landing
    # while the first call's "blocking" wait is in progress.
    original_dispatch = stub._dispatch_next

    def reentering_dispatch() -> None:
        click()  # re-entrant: must be a no-op
        original_dispatch()

    stub._dispatch_next = reentering_dispatch  # type: ignore[method-assign]

    click()
    assert stub.dispatched == 1, (
        "expected exactly one dispatch despite re-entrant click; "
        f"got {stub.dispatched}"
    )


# ---------------------------------------------------------------- P0-7

def test_empty_model_name_restores_default(tmp_path: Path) -> None:
    """A config.json with ``"model": {}`` must NOT silently propagate
    a fabricated model_path; load_config restores the default model.
    """
    cfg_path = Path(_cfg.config_path())
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps({"model": {}, "hub_folder": str(tmp_path)}),
        encoding="utf-8",
    )
    loaded = _cfg.load_config()
    assert loaded["model"]["name"] == "faster-whisper-large-v3"
    assert loaded["model"]["url"].startswith("http")
    # And model_path was recomputed against the (now non-empty) name.
    assert "faster-whisper-large-v3" in loaded["model_path"]


def test_empty_model_url_restores_default(tmp_path: Path) -> None:
    """``"model": {"name": "x", "url": ""}`` also triggers the reset."""
    cfg_path = Path(_cfg.config_path())
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps({
            "model": {"name": "x", "url": "", "md5": ""},
            "hub_folder": str(tmp_path),
        }),
        encoding="utf-8",
    )
    loaded = _cfg.load_config()
    assert loaded["model"]["name"] == "faster-whisper-large-v3"
    assert loaded["model"]["url"]


def test_non_dict_model_restores_default(tmp_path: Path) -> None:
    """A hand-edit setting ``"model": 42`` does not crash load_config."""
    cfg_path = Path(_cfg.config_path())
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps({"model": 42, "hub_folder": str(tmp_path)}),
        encoding="utf-8",
    )
    loaded = _cfg.load_config()
    # ``model`` was non-dict — the merge step earlier reverts to the
    # default before _apply_runtime_fallbacks even sees it.
    assert isinstance(loaded["model"], dict)
    assert loaded["model"]["name"] == "faster-whisper-large-v3"
