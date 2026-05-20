# Phase 3a — Acceptance

| ID    | What                                                                                  | How |
|-------|---------------------------------------------------------------------------------------|-----|
| 3A-T1 | `parse_progress_line` accepts the JSON `%(progress)j` shape and derives `percent`     | `python -m pytest tests/core/test_download_command.py -k "json_percent_derived" -q` |
| 3A-T2 | `HistoryDB` creates tables on first open, idempotent on second open                   | `python -m pytest tests/core/test_history_db.py::test_open_is_idempotent -q` |
| 3A-T3 | A finished download writes a row to `downloads` with non-null `output_paths`          | `python -m pytest tests/core/test_history_db.py::test_insert_and_finish_download -q` |
| 3A-T4 | Auto-transcribe wiring enqueues a `TranscriptionTask` with the right path + language  | `python -m pytest tests/core/test_auto_transcribe_wiring.py -q` |
| 3A-T5 | SponsorBlock flag is appended when `sponsorblock_categories` is non-empty             | `python -m pytest tests/core/test_download_command.py -k "sponsorblock" -q` |
| 3A-T6 | UI shows a new row in Transcription Queue after auto-transcribe-after-download        | `auto_transcribe_var` + `enqueue_transcription_from_download` (verified via wiring tests; manual GUI confirmation in BUILD smoke) |
| 3A-T7 | All prior acceptance tests still pass                                                 | `python -m pytest tests/ -q` |

## What landed in Phase 3a

- **`core/history.py`** — `HistoryDB` class wrapping SQLite at
  `user_data_dir() / "history.db"`. Schema covers `downloads` and
  `transcriptions`. `mark_interrupted()` runs on App startup so any row left
  in `running` after a previous crash flips to `interrupted`.
- **`core/config.py`** — `auto_transcribe_after_download` and
  `sponsorblock_categories` defaults landed (Phase 2a commit, but the
  consumers only became live in 3a).
- **`app/services/download_service.py`** — every download writes one
  history row on start (`insert_download`) and finalises on
  `_finish` with `finish_download(status, output_paths, detected_language)`.
  `build_download_command` reads `sponsorblock_categories` from config and
  threads them through to yt-dlp via `--sponsorblock-remove`.
- **`app/services/transcription_service.py`** — same idea for transcription
  rows: `insert_transcription` on dispatch, `finish_transcription` on
  `finish_task` with the duration, language, and output paths derived from
  `config["output_formats"]`.
- **`app/dialogs/statistics.py`** — read-only summary opened via
  `File → Statistics...`.
- **`app/widgets/platform.py`** — `open_folder(path, parent)` cross-platform
  helper used by the right-click `Open output folder` actions.
- **Right-click menus** — finished `Transcription Queue` rows now offer
  `Export → oTranscribe (.otr)`, `Open output folder`, `Re-run`, `Remove`.
  Finished `Download Videos` rows offer `Open download folder`, `Re-run`,
  `Remove`.

## Test count

```
core/history.py          — 11 tests in tests/core/test_history_db.py
auto_transcribe wiring    — 6 tests in tests/core/test_auto_transcribe_wiring.py
sponsorblock arg          — 1 test (test_download_command.py::sponsorblock)
progress JSON parsing     — 4 tests already in tests/core/test_download_command.py
```

Total Phase 3a additions: 17. Repository total now 136 (excluding the
two real-audio modules that auto-skip without network).

## What about config.json in dist/?

It is intentionally **not** copied into `dist/` by `build.bat`. Phase 1.2
migrated config to `%LOCALAPPDATA%\WhisperProject\config.json` and
`load_config()` synthesises a fresh one from `DEFAULT_CONFIG` on first
launch when nothing is found. Documented in `docs/BUILD.md`.
