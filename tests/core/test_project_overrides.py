"""Tests for per-folder ``.whisperproject.json`` overrides."""
from __future__ import annotations

import json

from core.config import (
    PROJECT_FILE_NAME,
    find_project_file,
    load_project_overrides,
    merge_project_overrides,
)


def test_find_project_file_in_same_directory(tmp_path):
    f = tmp_path / PROJECT_FILE_NAME
    f.write_text("{}", encoding="utf-8")
    media = tmp_path / "show.mp4"
    media.write_bytes(b"x")
    assert find_project_file(str(media)) == f


def test_find_project_file_walks_up(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    f = tmp_path / PROJECT_FILE_NAME
    f.write_text("{}", encoding="utf-8")
    media = deep / "show.mp4"
    media.write_bytes(b"x")
    assert find_project_file(str(media)) == f


def test_find_project_file_none_when_absent(tmp_path):
    media = tmp_path / "show.mp4"
    media.write_bytes(b"x")
    assert find_project_file(str(media)) is None


def test_load_project_overrides_returns_dict(tmp_path):
    (tmp_path / PROJECT_FILE_NAME).write_text(
        json.dumps({"output_formats": ["srt", "txt"], "hotwords": "Anthropic"}),
        encoding="utf-8",
    )
    out = load_project_overrides(str(tmp_path))
    assert out == {"output_formats": ["srt", "txt"], "hotwords": "Anthropic"}


def test_load_project_overrides_silent_on_bad_json(tmp_path):
    (tmp_path / PROJECT_FILE_NAME).write_text("{not valid", encoding="utf-8")
    assert load_project_overrides(str(tmp_path)) == {}


def test_load_project_overrides_silent_on_non_object(tmp_path):
    (tmp_path / PROJECT_FILE_NAME).write_text("[1,2,3]", encoding="utf-8")
    assert load_project_overrides(str(tmp_path)) == {}


def test_merge_project_overrides_shallow_top_level(tmp_path):
    (tmp_path / PROJECT_FILE_NAME).write_text(
        json.dumps({"hotwords": "OpenAI"}), encoding="utf-8"
    )
    base = {"hotwords": "", "output_formats": ["srt"]}
    out = merge_project_overrides(base, str(tmp_path / "a.wav"))
    assert out["hotwords"] == "OpenAI"
    assert out["output_formats"] == ["srt"]
    # Base must be unchanged (we deep-copied).
    assert base["hotwords"] == ""


def test_merge_project_overrides_nested_dict_one_level(tmp_path):
    (tmp_path / PROJECT_FILE_NAME).write_text(
        json.dumps({"model": {"name": "tiny"}}), encoding="utf-8"
    )
    base = {"model": {"name": "large", "url": "https://example/"}, "device": "cpu"}
    out = merge_project_overrides(base, str(tmp_path / "a.wav"))
    assert out["model"]["name"] == "tiny"
    # The url key is preserved by the deep merge.
    assert out["model"]["url"] == "https://example/"
    assert out["device"] == "cpu"


def test_merge_project_overrides_no_file_returns_base(tmp_path):
    base = {"hotwords": "kept"}
    out = merge_project_overrides(base, str(tmp_path / "x.wav"))
    assert out == base
