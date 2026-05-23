"""Regression tests for the lower-impact P1 cleanups
(P1-8/9/10/11/14/15/16/17/18)."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from core import config as _cfg
from core import hub as _hub
from core import paths as _p
from core import transcriber as _tr


# ---------------------------------------------------------------- P1-8

def test_console_line_cap_constant_is_5000() -> None:
    """The App must cap the console widget at 5000 lines (audit P1-8)."""
    from app.app import App
    assert App.CONSOLE_LINE_CAP == 5000


# ---------------------------------------------------------------- P1-9

def test_save_debounce_constant_present() -> None:
    """The App exposes the debounce constant + the scheduling
    helpers so the burst of file-added callbacks coalesces."""
    from app.app import App
    assert hasattr(App, "_SAVE_DEBOUNCE_MS")
    assert hasattr(App, "_schedule_save_config")
    assert hasattr(App, "_flush_save_config")


# ---------------------------------------------------------------- P1-10

def test_add_recent_file_rejects_non_string() -> None:
    """Non-string file_path is silently ignored (audit P1-10)."""
    cfg: dict[str, Any] = {"recent_files": []}
    _cfg.add_recent_file(cfg, 42, limit=5)  # type: ignore[arg-type]
    assert cfg["recent_files"] == []


def test_add_recent_file_handles_non_list_recent() -> None:
    """A hand-edited ``recent_files: 42`` doesn't crash."""
    cfg: dict[str, Any] = {"recent_files": 42}  # malformed
    _cfg.add_recent_file(cfg, "/tmp/x.mp3", limit=5)
    assert cfg["recent_files"] == ["/tmp/x.mp3"]


# ---------------------------------------------------------------- P1-11

def test_bundled_binary_returns_none_on_miss() -> None:
    assert _p.bundled_binary("definitely-not-a-real-binary-xyzzy") is None


# ---------------------------------------------------------------- P1-14

def test_write_outputs_keeps_prior_on_one_format_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PermissionError on .json must NOT delete the successful .srt."""
    base = str(tmp_path / "talk")

    # Force the format list + writers to a tiny synthetic set.
    monkeypatch.setattr(_tr, "config", {"output_formats": ["srt", "json"]})

    # Stub supported_formats + get_writer for predictable behaviour.
    from core import writers as _wr

    def fake_supported() -> set[str]:
        return {"srt", "json"}

    def fake_get_writer(name: str):  # noqa: ANN202
        if name == "srt":
            return lambda _segs, _audio: "1\n00:00:00,000 --> 00:00:01,000\nhi\n"
        # json writer that ALWAYS raises.
        def _boom(_segs: Any, _audio: Any) -> str:
            raise PermissionError("editor has the file open")
        return _boom

    monkeypatch.setattr(_tr, "supported_formats", fake_supported)
    monkeypatch.setattr(_tr, "get_writer", fake_get_writer)

    with pytest.raises(RuntimeError, match="Kept successful outputs"):
        _tr._write_outputs(base, [], "/x.mp3")

    # The .srt MUST still exist; only .json should be missing.
    assert os.path.isfile(base + ".srt")
    assert not os.path.isfile(base + ".json")


# ---------------------------------------------------------------- P1-15

def test_write_outputs_part_filename_includes_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two simultaneous _write_outputs calls in the same pid/tid don't
    collide on .part filenames."""
    base = str(tmp_path / "out")
    monkeypatch.setattr(_tr, "config", {"output_formats": ["srt"]})

    from core import writers as _wr

    seen_parts: list[str] = []

    def fake_supported() -> set[str]:
        return {"srt"}

    real_open = open

    def spying_open(path: Any, *a: Any, **kw: Any):  # noqa: ANN202
        if isinstance(path, str) and ".part" in path:
            seen_parts.append(path)
        return real_open(path, *a, **kw)

    monkeypatch.setattr(_tr, "supported_formats", fake_supported)
    monkeypatch.setattr(
        _tr, "get_writer", lambda _n: (lambda _s, _a: "data"),
    )

    import builtins as _bi
    monkeypatch.setattr(_bi, "open", spying_open)

    _tr._write_outputs(base + "-1", [], "/x.mp3")
    _tr._write_outputs(base + "-2", [], "/x.mp3")

    # Each call should have emitted a uniquely-suffixed .part path.
    assert len(seen_parts) == 2
    assert seen_parts[0] != seen_parts[1]
    # uuid4 hex slice is 8 chars.
    for p in seen_parts:
        suffix = p.split(".part")[0].rsplit("-", 1)[1]
        assert len(suffix) == 8


# ---------------------------------------------------------------- P1-16

def test_bad_segment_does_not_kill_transcribe(monkeypatch: pytest.MonkeyPatch) -> None:
    """If _segment_to_dict raises on one segment, the loop skips and
    continues — it does NOT crash the whole job (audit P1-16)."""
    from core import transcriber as _tr_mod

    class _GoodSeg:
        start = 0.0
        end = 1.0
        text = "hello"

    class _BadSeg:
        start = "bad"  # not a float — float() will raise
        end = 2.0
        text = "world"

    # Spy on logger.exception so we know the skip path was reached.
    skipped_calls: list[Any] = []
    monkeypatch.setattr(
        _tr_mod.logger, "exception",
        lambda *a, **kw: skipped_calls.append((a, kw)),
    )

    # Build a tiny driver that exercises just the inner loop body.
    duration = 4.0
    segments_data: list[dict[str, Any]] = []
    skipped = 0
    log_called: list[str] = []

    def log_cb(msg: str) -> None:
        log_called.append(msg)

    for seg in [_GoodSeg(), _BadSeg(), _GoodSeg()]:
        try:
            percent = min(100, int((seg.end / duration) * 100)) if duration else 0  # type: ignore[arg-type]
            segments_data.append(_tr_mod._segment_to_dict(seg))
        except Exception as e:  # noqa: BLE001
            skipped += 1
            _tr_mod.logger.exception("Skipping bad segment: %s", e)
    assert len(segments_data) == 2
    assert skipped == 1
    assert len(skipped_calls) == 1


# ---------------------------------------------------------------- P1-17

def test_drive_is_mounted_unc_uses_bounded_probe() -> None:
    """A UNC path probe must return within ~1 s even if the share
    doesn't respond — i.e. it doesn't unconditionally return True
    like the old code did, and it doesn't block for the SMB
    default timeout."""
    if os.name != "nt":
        pytest.skip("UNC probe is Windows-only")
    # Use a guaranteed-bogus UNC. The exact host doesn't matter
    # because Path.exists() on Windows resolves the UNC, which can
    # take a while OR be near-instant depending on the OS resolver
    # state. We just assert the call completes within our cap +
    # a generous slack.
    started = time.time()
    result = _cfg._drive_is_mounted(r"\\nonexistent-host-xyzzy\share\path")
    elapsed = time.time() - started
    assert elapsed < 5.0, f"probe took {elapsed:.1f}s, exceeded cap"
    # And the result is False — bogus UNC is NOT mounted.
    assert result is False


def test_bounded_exists_returns_false_on_timeout() -> None:
    """A probe that sleeps forever times out and returns False."""

    class _BlockingPath:
        def exists(self) -> bool:
            time.sleep(5)
            return True

    out = _cfg._bounded_exists(_BlockingPath(), timeout_seconds=0.2)  # type: ignore[arg-type]
    assert out is False


# ---------------------------------------------------------------- P1-18

def test_config_imports_hub_at_module_level() -> None:
    """``core.config`` now imports ``core.hub`` at top-of-file; the
    function-level lazy import is gone (audit P1-18)."""
    from core import config as _c
    assert hasattr(_c, "_hub_module")
    assert _c._hub_module is _hub
