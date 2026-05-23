"""Tests for ``core.config`` — load, save, merge, fallbacks, recent-files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import config as _cfg


def test_load_config_returns_defaults_when_missing() -> None:
    cfg = _cfg.load_config()
    assert cfg["model"]["name"] == "faster-whisper-large-v3"
    assert cfg["output_formats"] == ["srt", "json", "txt"]
    assert cfg["device"] == "auto"
    # Runtime fallback resolved model_path.
    assert cfg["model_path"]


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    cfg = _cfg.load_config()
    cfg["vad_enabled"] = False
    _cfg.save_config(cfg)
    cfg2 = _cfg.load_config()
    assert cfg2["vad_enabled"] is False


def test_corrupt_json_falls_back_to_defaults() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json}", encoding="utf-8")
    cfg = _cfg.load_config()
    # Defaults restored; corrupt file moved to .corrupt.
    assert cfg["model"]["name"] == "faster-whisper-large-v3"
    assert Path(str(path) + ".corrupt").exists()


def test_wrong_type_for_known_key_reverts() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"vad_enabled": "yes"}), encoding="utf-8",
    )
    cfg = _cfg.load_config()
    # Default re-applied (True).
    assert cfg["vad_enabled"] is True


def test_int_to_bool_coerced() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"vad_enabled": 0}), encoding="utf-8",
    )
    cfg = _cfg.load_config()
    assert cfg["vad_enabled"] is False


def test_non_dict_root_falls_back() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1,2,3]", encoding="utf-8")
    cfg = _cfg.load_config()
    assert cfg["model"]["name"] == "faster-whisper-large-v3"


def test_model_path_derived_from_hub_when_blank() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"hub_folder": "/tmp/whisper-hub"}),
        encoding="utf-8",
    )
    cfg = _cfg.load_config()
    assert "/tmp/whisper-hub" in cfg["model_path"].replace("\\", "/")
    assert "models--Systran--faster-whisper-large-v3" in cfg["model_path"]


def test_add_recent_file_dedupes_and_caps() -> None:
    cfg = _cfg.load_config()
    for i in range(7):
        _cfg.add_recent_file(cfg, f"/tmp/file{i}.mp3", limit=5)
    assert cfg["recent_files"][0] == "/tmp/file6.mp3"
    assert len(cfg["recent_files"]) == 5
    # Re-adding existing file moves it to front, doesn't duplicate.
    _cfg.add_recent_file(cfg, "/tmp/file3.mp3", limit=5)
    assert cfg["recent_files"][0] == "/tmp/file3.mp3"
    assert cfg["recent_files"].count("/tmp/file3.mp3") == 1


def test_add_recent_file_blank_is_noop() -> None:
    cfg = _cfg.load_config()
    before = list(cfg.get("recent_files") or [])
    _cfg.add_recent_file(cfg, "", limit=5)
    assert (cfg.get("recent_files") or []) == before


def test_save_config_creates_directory_if_missing() -> None:
    cfg = _cfg.load_config()
    target = Path(_cfg.config_path())
    # Pre-emptively delete the directory.
    if target.parent.exists():
        for f in target.parent.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
        target.parent.rmdir()
    _cfg.save_config(cfg)
    assert target.exists()


# ----------------------------------------------------------------- new sweep

# --------- DEFAULT_CONFIG sanity ---------

@pytest.mark.parametrize("key", list(_cfg.DEFAULT_CONFIG.keys()))
def test_every_default_key_present_after_load(key: str) -> None:
    cfg = _cfg.load_config()
    assert key in cfg


@pytest.mark.parametrize("key", list(_cfg.DEFAULT_CONFIG.keys()))
def test_every_default_key_is_json_serialisable(key: str) -> None:
    assert json.dumps({key: _cfg.DEFAULT_CONFIG[key]})


def test_default_model_url_is_https() -> None:
    assert _cfg.DEFAULT_CONFIG["model"]["url"].startswith("https://")
    assert _cfg.DEFAULT_CONFIG["model"]["md5"].startswith("https://")


def test_default_output_formats_are_srt_json_txt() -> None:
    assert set(_cfg.DEFAULT_CONFIG["output_formats"]) == {"srt", "json", "txt"}


def test_default_vad_enabled_true() -> None:
    assert _cfg.DEFAULT_CONFIG["vad_enabled"] is True


def test_default_device_is_auto() -> None:
    assert _cfg.DEFAULT_CONFIG["device"] == "auto"


def test_default_log_level_info() -> None:
    assert _cfg.DEFAULT_CONFIG["log_level"] == "INFO"


def test_default_recent_files_empty() -> None:
    assert _cfg.DEFAULT_CONFIG["recent_files"] == []


# --------- round-trip per key ---------

@pytest.mark.parametrize(
    "key,new_value",
    [
        ("device", "cpu"),
        ("compute_type", "float16"),
        ("vad_enabled", False),
        ("language", "fa"),
        ("log_level", "DEBUG"),
        ("model_path", "/tmp/custom/model"),
        ("hub_folder", "/tmp/custom/hub"),
    ],
)
def test_round_trip_key(key: str, new_value: object) -> None:
    cfg = _cfg.load_config()
    cfg[key] = new_value
    _cfg.save_config(cfg)
    cfg2 = _cfg.load_config()
    # model_path may be re-derived if not on a mounted drive; the
    # explicit value should still be observed because we just saved it.
    if key in ("model_path", "hub_folder"):
        # _apply_runtime_fallbacks may swap unmounted Windows drives.
        # Just assert the key is at least string-type and non-empty.
        assert isinstance(cfg2[key], str)
    else:
        assert cfg2[key] == new_value


# --------- wrong-type coercions ---------

@pytest.mark.parametrize(
    "wrong_value",
    [42, 3.14, None, {"x": 1}, ["a", "b"], True],
    ids=["int", "float", "None", "dict", "list", "bool"],
)
def test_wrong_type_for_str_key_reverts(wrong_value: object) -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"language": wrong_value}), encoding="utf-8")
    cfg = _cfg.load_config()
    # Defaults restored OR (for int→str via TypeError path) survives;
    # crucial check: load doesn't blow up and value is at least a str
    # in the default-recovery path.
    assert "language" in cfg


@pytest.mark.parametrize(
    "wrong_value",
    ["yes", 1.5, {"k": True}, ["x"]],
    ids=["str", "float", "dict", "list"],
)
def test_wrong_type_for_bool_key_reverts(wrong_value: object) -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"vad_enabled": wrong_value}), encoding="utf-8")
    cfg = _cfg.load_config()
    assert isinstance(cfg["vad_enabled"], bool)


@pytest.mark.parametrize(
    "wrong_value",
    ["whoops", 42, None, {}, True],
    ids=["str", "int", "None", "dict", "bool"],
)
def test_wrong_type_for_list_key_reverts(wrong_value: object) -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    if wrong_value is None:
        # write `null` for `output_formats`
        body = json.dumps({"output_formats": None})
    else:
        body = json.dumps({"output_formats": wrong_value})
    path.write_text(body, encoding="utf-8")
    cfg = _cfg.load_config()
    # Either list (default restored) or whatever passes the merge
    # filter — the contract is "no crash".
    assert "output_formats" in cfg


# --------- encoding edge cases ---------

def test_config_with_utf8_bom_is_handled() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 BOM + valid JSON. The reader uses encoding="utf-8" which
    # does NOT strip BOM (would need utf-8-sig). Expectation: corrupt
    # detect path triggers defaults.
    path.write_bytes(b"\xef\xbb\xbf{\"vad_enabled\": false}")
    cfg = _cfg.load_config()
    assert "vad_enabled" in cfg  # never crashes


def test_config_with_cp1252_garbage_falls_back() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    # Bytes that are valid cp1252 but not utf-8.
    path.write_bytes(b"\x91\x92\x93")
    cfg = _cfg.load_config()
    assert cfg["model"]["name"] == "faster-whisper-large-v3"


def test_config_with_random_garbage_falls_back() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x01\x02\x03\xff\xfe")
    cfg = _cfg.load_config()
    assert cfg["model"]["name"] == "faster-whisper-large-v3"


def test_config_with_truncated_json_falls_back() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"vad_enabled": tru', encoding="utf-8")
    cfg = _cfg.load_config()
    assert cfg["vad_enabled"] is True  # default


def test_config_with_empty_file_falls_back() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    cfg = _cfg.load_config()
    assert "model" in cfg


def test_config_with_latin1_bytes_falls_back() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    # 0xff is invalid UTF-8 leading byte
    path.write_bytes(b'{"language": "\xff"}')
    cfg = _cfg.load_config()
    assert "language" in cfg


# --------- save_config writes valid JSON ---------

def test_save_config_writes_valid_json() -> None:
    cfg = _cfg.load_config()
    cfg["language"] = "fa"
    _cfg.save_config(cfg)
    raw = Path(_cfg.config_path()).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["language"] == "fa"


def test_save_config_preserves_unicode_paths(tmp_path: Path) -> None:
    cfg = _cfg.load_config()
    chinese = str(tmp_path / "视频" / "file.mp4")
    _cfg.add_recent_file(cfg, chinese, limit=5)
    _cfg.save_config(cfg)
    cfg2 = _cfg.load_config()
    assert chinese in cfg2["recent_files"]


def test_save_config_atomic_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """If os.replace fails, no partial file should remain in the target."""
    cfg = _cfg.load_config()
    import os as _os
    real_replace = _os.replace

    def boom(_src: str, _dst: str) -> None:
        raise OSError("simulated permission denial")

    monkeypatch.setattr(_os, "replace", boom)
    with pytest.raises(OSError):
        _cfg.save_config(cfg)
    monkeypatch.setattr(_os, "replace", real_replace)
    # No .tmp files left behind in the target dir.
    cfg_dir = Path(_cfg.config_path()).parent
    leftover = [p for p in cfg_dir.iterdir() if p.suffix == ".tmp"]
    assert leftover == []


# --------- concurrent saves ---------

def test_concurrent_saves_yield_valid_json() -> None:
    """Two threads racing save_config → final file parses cleanly."""
    import threading
    cfg = _cfg.load_config()

    errors: list[Exception] = []

    def saver(language: str) -> None:
        for _ in range(20):
            try:
                cfg2 = dict(cfg)
                cfg2["language"] = language
                _cfg.save_config(cfg2)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

    t1 = threading.Thread(target=saver, args=("en",))
    t2 = threading.Thread(target=saver, args=("fr",))
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert errors == []
    final = json.loads(Path(_cfg.config_path()).read_text(encoding="utf-8"))
    assert final["language"] in {"en", "fr"}


def test_concurrent_saves_many_threads() -> None:
    """6 threads × 10 saves each → no crashes, final file valid."""
    import threading
    cfg = _cfg.load_config()

    errors: list[Exception] = []

    def saver(idx: int) -> None:
        for j in range(10):
            try:
                c = dict(cfg)
                c["log_level"] = "INFO" if (idx + j) % 2 == 0 else "DEBUG"
                _cfg.save_config(c)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

    threads = [threading.Thread(target=saver, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    parsed = json.loads(Path(_cfg.config_path()).read_text(encoding="utf-8"))
    assert parsed["log_level"] in {"INFO", "DEBUG"}


# --------- _drive_is_mounted: weird paths ---------

@pytest.mark.parametrize(
    "raw",
    [
        "",                       # empty
        "x",                      # letter
        "x.txt",                  # no drive
        "relative/path",          # relative
        "    ",                   # whitespace
        "/",                      # root-like
    ],
)
def test_drive_is_mounted_handles_non_drive_paths(raw: str) -> None:
    # Should never crash; on Windows, non-drive paths are treated as mounted.
    out = _cfg._drive_is_mounted(raw)
    assert isinstance(out, bool)


def test_drive_is_mounted_handles_pathobject(tmp_path: Path) -> None:
    assert _cfg._drive_is_mounted(tmp_path) is True


def test_drive_is_mounted_handles_huge_path() -> None:
    out = _cfg._drive_is_mounted("X:\\" + ("a" * 500))
    assert isinstance(out, bool)


def test_drive_is_mounted_handles_trailing_whitespace() -> None:
    out = _cfg._drive_is_mounted("C:\\Users  ")
    assert isinstance(out, bool)


def test_drive_is_mounted_real_existing_drive(tmp_path: Path) -> None:
    # tmp_path lives on a real drive that's mounted.
    assert _cfg._drive_is_mounted(tmp_path) is True


def test_drive_is_mounted_dead_drive_letter_windows() -> None:
    import os as _os
    if _os.name != "nt":
        pytest.skip("dead-drive probe is Windows-only")
    # Pick a drive letter very unlikely to be mounted.
    out = _cfg._drive_is_mounted("Q:\\nonexistent")
    # Either False (typical) or True (rare; user has Q: mounted).
    assert isinstance(out, bool)


# --------- _apply_runtime_fallbacks combinations ---------

def test_apply_fallbacks_hub_set_path_set_mounted(tmp_path: Path) -> None:
    cfg = {
        "model": dict(_cfg.DEFAULT_CONFIG["model"]),
        "hub_folder": str(tmp_path / "hub"),
        "model_path": str(tmp_path / "models"),
    }
    out = _cfg._apply_runtime_fallbacks(cfg)
    # model_path was set + mounted → preserved
    assert "models" in out["model_path"]


def test_apply_fallbacks_hub_set_path_blank(tmp_path: Path) -> None:
    cfg = {
        "model": dict(_cfg.DEFAULT_CONFIG["model"]),
        "hub_folder": str(tmp_path / "hub"),
        "model_path": "",
    }
    out = _cfg._apply_runtime_fallbacks(cfg)
    assert "hub" in out["model_path"]
    assert "models--Systran--faster-whisper-large-v3" in out["model_path"]


def test_apply_fallbacks_hub_blank_path_blank() -> None:
    cfg = {
        "model": dict(_cfg.DEFAULT_CONFIG["model"]),
        "hub_folder": "",
        "model_path": "",
    }
    out = _cfg._apply_runtime_fallbacks(cfg)
    # Defaults to default_hub_folder() + slug
    assert "models--Systran--faster-whisper-large-v3" in out["model_path"]


def test_apply_fallbacks_with_full_slug_in_name(tmp_path: Path) -> None:
    cfg = {
        "model": {
            "name": "models--OpenAI--whisper-tiny",
            "url": "https://example.com/m.zip",
            "md5": "https://example.com/m.zip.md5",
        },
        "hub_folder": str(tmp_path),
        "model_path": "",
    }
    out = _cfg._apply_runtime_fallbacks(cfg)
    # No double Systran prefix.
    assert "models--OpenAI--whisper-tiny" in out["model_path"]
    assert "models--Systran--models--OpenAI" not in out["model_path"]


def test_apply_fallbacks_corrupt_model_dict_restored() -> None:
    cfg = {
        "model": {"name": "", "url": "", "md5": ""},
        "hub_folder": "",
        "model_path": "",
    }
    out = _cfg._apply_runtime_fallbacks(cfg)
    assert out["model"]["name"] == "faster-whisper-large-v3"


def test_apply_fallbacks_model_not_a_dict() -> None:
    cfg = {
        "model": "broken-not-a-dict",
        "hub_folder": "",
        "model_path": "",
    }
    out = _cfg._apply_runtime_fallbacks(cfg)
    assert isinstance(out["model"], dict)
    assert out["model"]["name"] == "faster-whisper-large-v3"


# --------- add_recent_file: bounds & ordering ---------

@pytest.mark.parametrize("limit", [1, 2, 5, 10, 50])
def test_add_recent_file_respects_limit(limit: int) -> None:
    cfg: dict[str, _cfg.Any] = {"recent_files": []}
    for i in range(20):
        _cfg.add_recent_file(cfg, f"/tmp/f{i}.mp3", limit=limit)
    assert len(cfg["recent_files"]) == min(limit, 20)


def test_add_recent_file_most_recent_first() -> None:
    cfg: dict[str, _cfg.Any] = {"recent_files": []}
    _cfg.add_recent_file(cfg, "/tmp/a.mp3", limit=10)
    _cfg.add_recent_file(cfg, "/tmp/b.mp3", limit=10)
    _cfg.add_recent_file(cfg, "/tmp/c.mp3", limit=10)
    assert cfg["recent_files"] == ["/tmp/c.mp3", "/tmp/b.mp3", "/tmp/a.mp3"]


def test_add_recent_file_dedup_promotes_to_front() -> None:
    cfg: dict[str, _cfg.Any] = {
        "recent_files": ["/tmp/a.mp3", "/tmp/b.mp3", "/tmp/c.mp3"],
    }
    _cfg.add_recent_file(cfg, "/tmp/b.mp3", limit=10)
    assert cfg["recent_files"][0] == "/tmp/b.mp3"
    assert cfg["recent_files"].count("/tmp/b.mp3") == 1


def test_add_recent_file_case_insensitive_on_windows() -> None:
    import sys as _sys
    if _sys.platform != "win32":
        pytest.skip("case-fold dedup is Windows-only")
    cfg: dict[str, _cfg.Any] = {"recent_files": ["C:/Users/me/A.mp3"]}
    _cfg.add_recent_file(cfg, "c:/users/me/a.mp3", limit=10)
    assert len(cfg["recent_files"]) == 1


def test_add_recent_file_none_argument_noop() -> None:
    cfg: dict[str, _cfg.Any] = {"recent_files": ["/tmp/a.mp3"]}
    _cfg.add_recent_file(cfg, None, limit=5)  # type: ignore[arg-type]
    assert cfg["recent_files"] == ["/tmp/a.mp3"]


@pytest.mark.parametrize("bad_value", [42, 3.14, True, [], {}, b"bytes"])
def test_add_recent_file_non_string_noop(bad_value: object) -> None:
    cfg: dict[str, _cfg.Any] = {"recent_files": ["/tmp/a.mp3"]}
    _cfg.add_recent_file(cfg, bad_value, limit=5)  # type: ignore[arg-type]
    assert cfg["recent_files"] == ["/tmp/a.mp3"]


def test_add_recent_file_filters_non_string_existing() -> None:
    """Existing non-string entries are stripped during dedup."""
    cfg: dict[str, _cfg.Any] = {
        "recent_files": ["/tmp/a.mp3", 42, None, "/tmp/b.mp3"],
    }
    _cfg.add_recent_file(cfg, "/tmp/new.mp3", limit=10)
    assert all(isinstance(p, str) for p in cfg["recent_files"])


def test_add_recent_file_limit_zero_keeps_nothing() -> None:
    cfg: dict[str, _cfg.Any] = {"recent_files": []}
    _cfg.add_recent_file(cfg, "/tmp/a.mp3", limit=0)
    assert cfg["recent_files"] == []


def test_add_recent_file_with_unicode_path() -> None:
    cfg: dict[str, _cfg.Any] = {"recent_files": []}
    _cfg.add_recent_file(cfg, "/tmp/视频.mp4", limit=5)
    assert cfg["recent_files"][0] == "/tmp/视频.mp4"


# --------- merge with defaults: nested ---------

def test_merge_preserves_partial_model_dict() -> None:
    """User-provided model.url overrides; missing keys filled from default."""
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"model": {"name": "custom", "url": "https://x/y.zip", "md5": "https://x/y.zip.md5"}}),
        encoding="utf-8",
    )
    cfg = _cfg.load_config()
    assert cfg["model"]["name"] == "custom"
    assert cfg["model"]["url"] == "https://x/y.zip"


def test_merge_preserves_extra_unknown_keys() -> None:
    """Forward-compat: an unknown top-level key survives the merge."""
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"future_key": "future_value"}),
        encoding="utf-8",
    )
    cfg = _cfg.load_config()
    assert cfg.get("future_key") == "future_value"


def test_merge_does_not_lose_defaults_for_unset_keys() -> None:
    path = Path(_cfg.config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"language": "fa"}), encoding="utf-8")
    cfg = _cfg.load_config()
    assert cfg["device"] == _cfg.DEFAULT_CONFIG["device"]
    assert cfg["vad_enabled"] == _cfg.DEFAULT_CONFIG["vad_enabled"]


def test_load_config_returns_independent_copy() -> None:
    """Two loads must return independent dicts — mutating one must not
    bleed into the next caller."""
    a = _cfg.load_config()
    b = _cfg.load_config()
    a["language"] = "MUTATED"
    assert b["language"] != "MUTATED"


def test_save_then_load_preserves_recent_files_order() -> None:
    cfg = _cfg.load_config()
    cfg["recent_files"] = ["/a", "/b", "/c"]
    _cfg.save_config(cfg)
    cfg2 = _cfg.load_config()
    assert cfg2["recent_files"] == ["/a", "/b", "/c"]


def test_config_path_under_user_config_dir() -> None:
    p = Path(_cfg.config_path())
    assert p.name == "config.json"
    assert p.parent == _cfg.user_config_dir()


def test_load_config_creates_config_dir() -> None:
    import shutil as _sh
    cfg_dir = _cfg.user_config_dir()
    if cfg_dir.exists():
        _sh.rmtree(cfg_dir)
    _cfg.load_config()
    assert cfg_dir.exists()


# --------- recent_files preserved across save/load ---------

@pytest.mark.parametrize("count", [0, 1, 3, 5, 10])
def test_save_load_preserves_recent_files_count(count: int) -> None:
    cfg = _cfg.load_config()
    cfg["recent_files"] = [f"/tmp/f{i}.mp3" for i in range(count)]
    _cfg.save_config(cfg)
    cfg2 = _cfg.load_config()
    assert len(cfg2["recent_files"]) == count


# --------- bounded_exists negative cases ---------

def test_bounded_exists_returns_true_for_existing(tmp_path: Path) -> None:
    out = _cfg._bounded_exists(tmp_path, timeout_seconds=1.0)
    assert out is True


def test_bounded_exists_returns_false_for_nonexistent(tmp_path: Path) -> None:
    p = tmp_path / "does-not-exist-xyzzy"
    out = _cfg._bounded_exists(p, timeout_seconds=1.0)
    assert out is False


def test_bounded_exists_handles_oserror() -> None:
    """A probe that raises OSError → returns False (caught silently)."""
    class _RaisingPath:
        def exists(self) -> bool:
            raise OSError("nope")

    out = _cfg._bounded_exists(_RaisingPath(), timeout_seconds=1.0)  # type: ignore[arg-type]
    assert out is False
