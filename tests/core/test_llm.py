"""Tests for the local LLM panel (download + runner + parsing)."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core import llm


# ---------- availability -------------------------------------------------------


def test_runtime_available_false_when_module_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "llama_cpp", None)
    assert llm.runtime_available() is False
    assert "llama-cpp-python" in llm.runtime_availability_reason()


# ---------- model file presence ------------------------------------------------


def test_is_model_present_false_when_missing(tmp_path):
    assert llm.is_model_present(tmp_path / "no-such.gguf") is False


def test_is_model_present_false_when_too_small(tmp_path):
    p = tmp_path / "tiny.gguf"
    p.write_bytes(b"x" * 1024)  # 1 KB — below the sanity threshold
    assert llm.is_model_present(p) is False


def test_is_model_present_true_when_large_enough(tmp_path):
    p = tmp_path / "big.gguf"
    # 101 MB of zeros — fast to write via seek+truncate.
    with p.open("wb") as f:
        f.seek(101_000_000)
        f.write(b"\0")
    assert llm.is_model_present(p) is True


# ---------- download -----------------------------------------------------------


def test_download_skips_when_model_already_present(tmp_path, monkeypatch):
    dest = tmp_path / "model.gguf"
    with dest.open("wb") as f:
        f.seek(101_000_000)
        f.write(b"\0")
    # If urlopen is called we'd see ConnectionRefused; the skip path
    # must never reach it.
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        lambda *a, **kw: pytest.fail("download attempted"))
    logs: list[str] = []
    result = llm.download_default_model(log=logs.append, dest=dest)
    assert result == str(dest)
    assert any("already present" in s for s in logs)


def test_download_writes_atomically_via_part(tmp_path, monkeypatch):
    """Successful download must produce the final file via os.replace
    and leave no .part residue."""
    dest = tmp_path / "model.gguf"
    payload = b"\x47\x47\x55\x46" + b"\0" * 1024  # GGUF magic + filler

    class _FakeResponse:
        headers = {"content-length": str(len(payload))}

        def __init__(self):
            self._data = payload
            self._pos = 0

        def read(self, chunk_size: int) -> bytes:
            if self._pos >= len(self._data):
                return b""
            chunk = self._data[self._pos:self._pos + chunk_size]
            self._pos += len(chunk)
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        lambda *a, **kw: _FakeResponse())
    # Bypass the post-download size sanity check so the test isn't
    # forced to fabricate 100 MB of payload.
    monkeypatch.setattr(llm, "is_model_present", lambda path=None: False)
    result = llm.download_default_model(dest=dest)
    assert Path(result).exists()
    assert (tmp_path / "model.gguf").read_bytes()[:4] == b"GGUF"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".part")]
    assert leftovers == []


def test_download_cleans_up_part_on_cancel(tmp_path, monkeypatch):
    """A mid-flight cancel must delete the .part file."""
    import threading
    dest = tmp_path / "model.gguf"
    cancel = threading.Event()
    cancel.set()  # already cancelled

    class _FakeResponse:
        headers = {"content-length": "10000"}

        def read(self, _chunk_size: int) -> bytes:
            return b"x" * 1000

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        lambda *a, **kw: _FakeResponse())
    monkeypatch.setattr(llm, "is_model_present", lambda path=None: False)
    with pytest.raises(RuntimeError, match="cancelled"):
        llm.download_default_model(dest=dest, cancel_event=cancel)
    assert not (dest.with_suffix(dest.suffix + ".part")).exists()


# ---------- LLMRunner --------------------------------------------------------


def test_runner_load_raises_when_runtime_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "runtime_available", lambda: False)
    r = llm.LLMRunner(llm.LLMConfig(model_path=str(tmp_path / "x.gguf")))
    with pytest.raises(llm.LLMUnavailable):
        r.load()


def test_runner_load_raises_when_model_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "runtime_available", lambda: True)
    fake_llama_cpp = types.ModuleType("llama_cpp")
    fake_llama_cpp.Llama = MagicMock()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp)
    r = llm.LLMRunner(llm.LLMConfig(model_path=str(tmp_path / "no.gguf")))
    with pytest.raises(FileNotFoundError):
        r.load()


def test_runner_load_constructs_llama_once(tmp_path, monkeypatch):
    """Second load() call must be a no-op (no double instantiation)."""
    monkeypatch.setattr(llm, "runtime_available", lambda: True)
    fake_module = types.ModuleType("llama_cpp")
    fake_llama_class = MagicMock()
    fake_module.Llama = fake_llama_class  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_module)
    model_file = tmp_path / "m.gguf"
    model_file.write_bytes(b"\0" * 100)
    r = llm.LLMRunner(llm.LLMConfig(model_path=str(model_file)))
    r.load()
    r.load()
    assert fake_llama_class.call_count == 1


def test_runner_summarise_returns_completion_text(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "runtime_available", lambda: True)
    fake_module = types.ModuleType("llama_cpp")

    class _FakeLlama:
        def __init__(self, **_kw):
            pass

        def create_chat_completion(self, **kw):
            return {
                "choices": [
                    {"message": {"content": "- bullet one\n- bullet two"}}
                ]
            }

    fake_module.Llama = _FakeLlama  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_module)
    model_file = tmp_path / "m.gguf"
    model_file.write_bytes(b"\0" * 100)
    r = llm.LLMRunner(llm.LLMConfig(model_path=str(model_file)))
    out = r.summarise("This is a transcript about widgets.")
    assert "bullet one" in out
    assert "bullet two" in out


def test_runner_action_items_parses_json_array(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "runtime_available", lambda: True)
    fake_module = types.ModuleType("llama_cpp")

    class _FakeLlama:
        def __init__(self, **_kw):
            pass

        def create_chat_completion(self, **kw):
            return {
                "choices": [
                    {"message": {"content": '["call Alice", "email Bob"]'}}
                ]
            }

    fake_module.Llama = _FakeLlama  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_module)
    model_file = tmp_path / "m.gguf"
    model_file.write_bytes(b"\0" * 100)
    r = llm.LLMRunner(llm.LLMConfig(model_path=str(model_file)))
    items = r.action_items("transcript")
    assert items == ["call Alice", "email Bob"]


# ---------- JSON list parser ---------------------------------------------------


def test_parse_json_list_strict_array():
    assert llm._parse_json_list('["a", "b", "c"]') == ["a", "b", "c"]


def test_parse_json_list_strips_markdown_fence():
    raw = '```json\n["x", "y"]\n```'
    assert llm._parse_json_list(raw) == ["x", "y"]


def test_parse_json_list_strips_leading_prose():
    raw = 'Here are the items:\n["one", "two"]'
    assert llm._parse_json_list(raw) == ["one", "two"]


def test_parse_json_list_returns_empty_on_garbage():
    assert llm._parse_json_list("not json at all") == []
    assert llm._parse_json_list("") == []
    assert llm._parse_json_list("[unclosed") == []


def test_parse_json_list_coerces_numbers_to_strings():
    assert llm._parse_json_list('[1, "two", 3.5]') == ["1", "two", "3.5"]


def test_parse_json_list_rejects_non_array():
    assert llm._parse_json_list('{"key": "value"}') == []
