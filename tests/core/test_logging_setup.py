"""Tests for ``core.logging_setup``."""
from __future__ import annotations

import io
import logging
from pathlib import Path

import pytest

from core import logging_setup as _ls


@pytest.fixture(autouse=True)
def _reset_logging_state() -> None:
    """Each test starts with the module's _configured flag reset."""
    yield
    # Tear down: remove the handlers we added so the next test starts clean.
    root = logging.getLogger()
    for h in list(root.handlers):
        try:
            h.close()
        except OSError:
            pass
        root.removeHandler(h)
    _ls._configured = False


# ---------------------------------------------------------------- setup_logging


def test_setup_logging_returns_log_path() -> None:
    p = _ls.setup_logging("INFO")
    assert isinstance(p, Path)
    assert p.name == "app.log"


def test_setup_logging_creates_log_dir() -> None:
    _ls.setup_logging("INFO")
    assert _ls.user_log_dir().exists()


@pytest.mark.parametrize(
    "level",
    ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
)
def test_setup_logging_sets_level(level: str) -> None:
    _ls.setup_logging(level)
    expected = getattr(logging, level)
    assert logging.getLogger().level == expected


@pytest.mark.parametrize(
    "level",
    ["debug", "info", "warning", "error", "critical"],
)
def test_setup_logging_case_insensitive(level: str) -> None:
    _ls.setup_logging(level)
    expected = getattr(logging, level.upper())
    assert logging.getLogger().level == expected


def test_setup_logging_unknown_level_defaults_to_info() -> None:
    _ls.setup_logging("BOGUS")
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_idempotent_does_not_double_add_handlers() -> None:
    """Second call must not add a second pair of handlers."""
    _ls.setup_logging("INFO")
    handlers_first = len(logging.getLogger().handlers)
    _ls.setup_logging("DEBUG")
    handlers_second = len(logging.getLogger().handlers)
    assert handlers_first == handlers_second


def test_setup_logging_updates_level_on_second_call() -> None:
    """First call INFO, second call DEBUG → effective level becomes DEBUG."""
    _ls.setup_logging("INFO")
    _ls.setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_writes_to_file() -> None:
    p = _ls.setup_logging("INFO")
    logging.getLogger("test").warning("test message %d", 42)
    # Flush all handlers
    for h in logging.getLogger().handlers:
        h.flush()
    text = p.read_text(encoding="utf-8", errors="replace")
    assert "test message 42" in text


def test_setup_logging_with_custom_stream() -> None:
    stream = io.StringIO()
    _ls.setup_logging("INFO", stream=stream)
    logging.getLogger("test").warning("custom stream msg")
    for h in logging.getLogger().handlers:
        h.flush()
    out = stream.getvalue()
    assert "custom stream msg" in out


def test_setup_logging_silences_third_parties() -> None:
    _ls.setup_logging("DEBUG")
    for name in ("urllib3", "requests", "huggingface_hub", "filelock"):
        assert logging.getLogger(name).level == logging.WARNING


def test_setup_logging_file_uses_utf8_encoding() -> None:
    p = _ls.setup_logging("INFO")
    logging.getLogger("test").warning("视频 unicode")
    for h in logging.getLogger().handlers:
        h.flush()
    text = p.read_text(encoding="utf-8")
    assert "视频" in text


# ---------------------------------------------------------------- read_recent_log


def test_read_recent_log_returns_empty_string_when_missing() -> None:
    # Even though our autouse fixture creates user_log_dir, the log file
    # may not have been written to yet.
    p = _ls.user_log_dir() / _ls.LOG_FILENAME
    if p.exists():
        p.unlink()
    assert _ls.read_recent_log() == ""


def test_read_recent_log_returns_tail() -> None:
    p = _ls.user_log_dir() / _ls.LOG_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("line1\nline2\nline3\n", encoding="utf-8")
    out = _ls.read_recent_log(lines=2)
    assert "line2" in out
    assert "line3" in out


def test_read_recent_log_more_lines_than_file() -> None:
    p = _ls.user_log_dir() / _ls.LOG_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("only line\n", encoding="utf-8")
    out = _ls.read_recent_log(lines=200)
    assert "only line" in out


def test_read_recent_log_zero_lines_capped_to_one() -> None:
    p = _ls.user_log_dir() / _ls.LOG_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("a\nb\nc\n", encoding="utf-8")
    out = _ls.read_recent_log(lines=0)
    # max(1, 0) → keeps at least one line.
    assert "c" in out


def test_read_recent_log_negative_lines_capped() -> None:
    p = _ls.user_log_dir() / _ls.LOG_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("a\nb\nc\n", encoding="utf-8")
    out = _ls.read_recent_log(lines=-50)
    assert "c" in out


def test_read_recent_log_unicode() -> None:
    p = _ls.user_log_dir() / _ls.LOG_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("视频 line\n", encoding="utf-8")
    out = _ls.read_recent_log()
    assert "视频" in out


# ---------------------------------------------------------------- constants


def test_log_format_has_asctime() -> None:
    assert "asctime" in _ls.LOG_FORMAT


def test_log_format_has_levelname() -> None:
    assert "levelname" in _ls.LOG_FORMAT


def test_log_filename() -> None:
    assert _ls.LOG_FILENAME == "app.log"


def test_log_max_bytes_at_least_one_mb() -> None:
    assert _ls.LOG_MAX_BYTES >= 1024 * 1024


def test_log_backup_count_positive() -> None:
    assert _ls.LOG_BACKUP_COUNT > 0
