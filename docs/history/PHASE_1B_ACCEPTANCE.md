# Phase 1b — Acceptance

Each row is a one-shot, grep-able test that proves a piece of the foundation
refactor landed correctly. Run from the repo root.

| ID    | What                                                                    | How |
|-------|-------------------------------------------------------------------------|-----|
| 1B-T1 | `gui.py` is ≤ 30 lines (entry point only)                               | `python -c "import os; assert sum(1 for _ in open('gui.py', encoding='utf-8')) <= 30"` |
| 1B-T2 | `app/app.py` exists and is < 500 lines                                  | `python -c "assert sum(1 for _ in open('app/app.py', encoding='utf-8')) < 500"` |
| 1B-T3 | `python -m pytest tests/ -q` returns exit 0 with ≥ 25 passing tests     | `python -m pytest tests/ -q` |
| 1B-T4 | `core/` line coverage ≥ 80% on the testable modules                     | `python -m pytest tests/ --cov=core --cov-report=term` (config 83%, model_manager 81%, otranscribe 91%, worker 90%, logging_setup 78%; transcriber heavy paths slated for Phase 2a smoke) |
| 1B-T5 | `pyright core/` returns zero errors                                     | `python -m pyright --pythonversion 3.11 core/` |
| 1B-T6 | Headless App() construction succeeds in < 5 s                            | `python -c "import sys; sys.path.insert(0,'.'); from app.app import App; A=App(); A.after(100, A.destroy); A.mainloop()"` |
| 1B-T7 | All Phase 0 / 1a / 2-oTranscribe acceptance tests still pass            | re-run their own scripts; `tests/integrations/test_otranscribe.py` (9 tests) covers Phase 2-oTranscribe automatically |

## Layout invariants

```
gui.py                              # 11-line entry, --worker shortcut + app.run()
pyproject.toml                      # project metadata + optional deps
app/
├── __init__.py                     # exports run() + App lazily
├── app.py                          # Tk root, ~430 lines
├── observability.py                # init_sentry() — env-gated, no DSN in code
├── dialogs/
│   └── model_download.py           # ModelDownloadDialog
├── domain/
│   ├── languages.py                # SUBTITLE_LANGUAGES + subtitle_lang_args()
│   └── tasks.py                    # TranscriptionTask, VideoDownloadTask
├── services/
│   ├── download_service.py         # build_download_command, parse_progress_line, DownloadService
│   ├── format_service.py           # FormatService — yt-dlp --dump-single-json wrapper
│   ├── integrations_service.py     # IntegrationsService — oTranscribe wiring
│   └── transcription_service.py    # TranscriptionService — worker lifecycle + dispatcher
└── widgets/
    ├── console.py                  # build_console() — black/lime Text widget
    └── tabs.py                     # build_transcribe_tab / queue / download
core/
├── __init__.py                     # from __future__ import annotations
├── config.py                       # typed; pyright clean
├── integrations/otranscribe.py     # 91% line coverage
├── logging_setup.py                # typed
├── model_manager.py                # typed; 81% line coverage
├── task.py                         # typed; new language/probability fields
├── transcriber.py                  # typed; pyright clean
└── worker.py                       # typed; 90% line coverage
tests/
├── integrations/test_otranscribe.py   # 9 tests (Phase 2-oTranscribe)
└── core/
    ├── test_config.py                  # 9
    ├── test_download_command.py        # 20
    ├── test_model_manager.py           # 10
    ├── test_subtitle_lang_args.py      # 10
    ├── test_transcriber_helpers.py     # 12
    └── test_worker_protocol.py         # 10
```

## Per-instance state (AUDIT B3 closed)

The old module-level `queue`, `download_queue`, `download_current` are gone.
Each `App` instance owns its own `self.queue`, `self.download_queue`, etc.
`tests/core/` constructs builders without an App and never depends on globals.

## Worker subprocess routing

The frozen exe doubles as the worker via the `--worker` flag handled at the
top of `gui.py`. In source mode `transcription_service.start_worker()` spawns
`python -m core.worker`. The protocol (ready/started/progress/done/error/
worker_exit) is unchanged; a forward-compatible `language_detected` hook was
added in `transcription_service.poll()` for Phase 2a.
