# Phases 1b + 2a + 3a — Master Hands-Off Brief

Self-contained brief for a single Claude Code (or Claude Console) session acting as the **fifth architect**. You will land three phases in one session, hands-off, with frequent checkpoint commits and per-phase pushes. The order is non-negotiable: 1b → 2a → 3a. Refactoring after features means resolving merge conflicts you could have avoided.

This is the most ambitious brief in the project's history. Plan for 4–8 hours of focused work. Push after every phase so partial success survives any session-ending event.

---

## Your role and authorization

You are the **fifth architect**. Phases 0, 1a, and 2-oTranscribe are on `origin/master` at commit `985ffa6`. Read `docs/SESSION_LOG.md` from the top to understand how prior sessions worked.

**Scope:** implement Phase 1b (foundation refactor), Phase 2a (Whisper masterpiece), Phase 3a (yt-dlp killer features). Run all real and acceptance tests. Compile the app with PyInstaller and smoke-test the binary. Commit incrementally on `master`. Push after every phase. Emit a combined JSON report at the very end.

**Authorized actions:**

- `pip install` any package listed below or any its transitive dependency
- Edit any file in the repository
- Create new files and directories (no new top-level layout beyond `app/`, `tests/`, `dist/`, `build/`)
- Run the GUI for smoke tests (headless and live)
- Run `pytest`, `ruff`, `pyright`
- Run PyInstaller and execute the built binary for ≤ 30 seconds
- Commit on `master` with descriptive messages
- Push to `origin/master` after each phase passes its acceptance
- Append to `docs/SESSION_LOG.md` after each phase
- Append a row to relevant tables in `docs/ROADMAP.md`, `docs/AUDIT.md`, `docs/CHANGELOG.md`

**Forbidden actions:**

- Create new branches; rebase; amend past commits; force-push
- Embed any token in code, commits, or config files
- Delete or rename Phase 0 / Phase 1 / Phase 2-oTranscribe files outside the explicit refactor in Phase 1b
- Skip phases or merge them
- Declare any phase "done" with a failing test
- Add a runtime dependency not justified by a roadmap item
- Touch `bin/yt-dlp.exe`, `bin/ffmpeg.exe`, `bin/ffprobe.exe` — these are vendored

**Required reading before you start:**

1. `README.md`
2. `docs/SESSION_LOG.md`
3. `docs/ARCHITECTURE.md`
4. `docs/AUDIT.md` (sections B and D for context on Phase 1b)
5. `docs/ROADMAP.md` Phase 1, Phase 2, Phase 3
6. `docs/DECISIONS.md`
7. `docs/PHASE_0_ACCEPTANCE.md` and `docs/PHASE_1_ACCEPTANCE.md` (you will re-run both)
8. `docs/integrations/otranscribe-acceptance.md` (you will re-run this too)

---

## Sequence and checkpoints

```
Pre-flight  ─►  Phase 1b  ─►  Phase 2a  ─►  Phase 3a  ─►  Final compile  ─►  Final report
                  │             │             │             │
                  └─ push       └─ push       └─ push       └─ push if compile clean
```

Between every phase: stop, run **all prior acceptance suites** (Phase 0, 1a, 2-oTranscribe, plus every phase you have already completed in this session). Fix regressions before continuing.

**Stop conditions** (do not push partial work):

- A single failing test, after **three repair iterations** in a row, on a single test — stop, emit JSON report, exit
- More than **300 commits** in one session — stop, emit report, exit
- More than **15,000 net lines added across `core/`, `app/`, `tests/`** — stop, emit report, exit
- A PyInstaller build that crashes within 5 seconds of launch in the final compile step — mark Phase 3a `COMPLETE_BUT_BUILD_BROKEN`, emit report, do not push the final phase

**Emergency hatch:** if any phase fails after iterations, **all previously-pushed phases stay pushed**. The session can be resumed later from the point of failure by a sixth architect with an addendum brief.

---

## Pre-flight

```bash
cd "C:/Users/Owner/Desktop/whisper_project_claude/whisper_project_direct_download_v2"
git status                       # must be clean
git rev-parse HEAD               # capture for the report
git log --oneline -5             # confirm 985ffa6 is at the top
python -V                        # confirm 3.14 (or 3.11+)
python -c "import sv_ttk, platformdirs, faster_whisper; print('PREFLIGHT_OK')"
python -m pytest tests/ -q       # all current tests must pass before you start
```

If any pre-flight check fails, stop and report. Do not touch anything.

---

## Phase 1b — Foundation refactor

Goal: turn a 1233-line `gui.py` + a `core/` with no tests + no type hints into a maintainable codebase that the next two phases can safely extend.

### 1b.1 — Split `gui.py` into `app/` package

Target layout (the conservative split — keep the `App` class itself in one file):

```
app/
├── __init__.py
├── app.py                              # App class, < 450 lines
├── dialogs/
│   ├── __init__.py
│   └── model_download.py               # ModelDownloadDialog
├── domain/
│   ├── __init__.py
│   ├── tasks.py                        # TranscriptionTask, VideoDownloadTask
│   └── languages.py                    # SUBTITLE_LANGUAGES
├── services/
│   ├── __init__.py
│   ├── format_service.py               # lookup_formats, poll_format_events
│   ├── download_service.py             # build_download_command, build_subtitle_command, process_download_queue, poll_download_events, maybe_update_yt_dlp
│   ├── transcription_service.py        # start_worker, poll_worker_events, finish_worker_task
│   └── integrations_service.py         # the oTranscribe wiring you'll keep on master
└── widgets/
    ├── __init__.py
    └── console.py                      # the Text widget
```

- `gui.py` at root becomes a 5-line entry point that imports and runs `app.App`. Do NOT delete it — many shortcuts and scripts use `python gui.py`.
- The `App` class loses methods to the service modules. Each service receives the `App` instance in its constructor and exposes verbs the App can call. State that lived as `self.foo` in App becomes `self.service.foo` or stays on App with a service that reads it.
- Keep all event queues on the App. Services produce events; the App polls them. The Tk main thread invariant must not weaken.
- Update all imports across `core/` if needed.
- Commit after each service is extracted. Expected ~6 commits.

### 1b.2 — Tests for `core/`

Land a proper `tests/` tree (it already exists with `tests/integrations/`). New files:

- `tests/test_config.py` — fallback to defaults, atomic write, corrupt-JSON quarantine, `_apply_runtime_fallbacks` for unreachable Windows drives, migration of legacy `config.json` location
- `tests/test_model_manager.py` — mock `requests` via `responses` (`pip install responses`), exercise: full download, partial download resume via `Range`, MD5 mismatch triggers redownload, cancel mid-download raises `DownloadCancelled`, missing manifest URL fails clearly
- `tests/test_worker_protocol.py` — spawn `python -m core.worker`, write `{"action":"shutdown"}` to stdin, assert clean exit. Then spawn another, write a `transcribe` command pointing at a fixture WAV (see "real tests" below), assert event sequence `ready → started → progress(*) → done`
- `tests/test_subtitle_lang_args.py` — pure-function test of the comma-joining logic
- `tests/test_download_command.py` — exhaustive matrix of (mode, output_format, audio_choice, video_choice) producing expected yt-dlp argv

Target: 80% line coverage on `core/` measured by `coverage`.

Add `pyproject.toml`:

```toml
[project]
name = "whisper-project"
version = "0.4.0"
requires-python = ">=3.11"
dependencies = [
    "faster-whisper>=1.0.3",
    "requests>=2.31.0",
    "sv-ttk>=2.6.0",
    "platformdirs>=4.0.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=4.0", "responses>=0.24", "ruff>=0.4", "pyright>=1.1.350"]

[tool.pyright]
include = ["core", "app"]
strict = ["core"]
reportMissingTypeStubs = false

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"

[tool.ruff]
target-version = "py311"
line-length = 110
```

### 1b.3 — Type hints on `core/`

Pass `pyright --strict core/` cleanly. Add `from __future__ import annotations` at the top of every `core/` module. Annotate every public function. Internals can use inferred types when obvious.

### 1b.4 — Sentry (optional, env-gated)

```python
# app/observability.py
import os, logging
def init_sentry():
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn: return False
    import sentry_sdk
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0, send_default_pii=False)
    logging.getLogger(__name__).info("Sentry crash reporting enabled")
    return True
```

Call from `app/app.py` after `setup_logging`. Add `sentry-sdk>=1.40.0` to `[project.optional-dependencies].crash_reporting` (not active deps). Never commit a DSN.

### 1b.5 — Phase 1b acceptance

Create `docs/PHASE_1B_ACCEPTANCE.md` with grep-able tests:

| ID | What | How |
|---|---|---|
| 1B-T1 | `gui.py` is ≤ 30 lines (entry point only) | `python -c "import os; assert sum(1 for _ in open('gui.py', encoding='utf-8')) <= 30"` |
| 1B-T2 | `app/app.py` exists and is < 500 lines | line count |
| 1B-T3 | `python -m pytest tests/ -q` returns exit 0 with ≥ 25 passing tests | shell |
| 1B-T4 | `coverage run -m pytest && coverage report --include='core/*' --fail-under=80` | shell |
| 1B-T5 | `pyright --strict core/` returns zero errors | shell |
| 1B-T6 | `python gui.py` headless smoke (App() with monkey-patched workers) succeeds in < 5 s | scripted |
| 1B-T7 | All Phase 0, Phase 1a, Phase 2-oTranscribe acceptance tests still pass | re-run |

### 1b.6 — Compile checkpoint (light)

```bash
python -c "import app; print('PACKAGE_OK')"
ruff check core/ app/ tests/
```

### 1b.7 — Push checkpoint

Commit messages start with `Phase 1b.N:` where N matches the section. After all 1b sections green, push:

```bash
git push origin master
```

Append a `Session 5 / Phase 1b` block to `docs/SESSION_LOG.md`. Update `docs/CHANGELOG.md` Unreleased and `docs/ROADMAP.md` Progress snapshot.

---

## Phase 2a — Whisper masterpiece

Goal: make transcription quality and speed actually competitive with Buzz / CheshireCC / WhisperX. This is the most user-visible phase.

### 2a.1 — VAD (Voice Activity Detection)

Wire `vad_filter=True` with configurable `vad_parameters` into `core/transcriber.transcribe`. Default ON. Settings keys:

```python
"vad_enabled": True,
"vad_min_silence_ms": 500,
"vad_threshold": 0.5,
"vad_speech_pad_ms": 400,
```

UI: a checkbox `Voice Activity Detection` on the Transcribe tab, plus an `Advanced...` button that opens a small dialog with two sliders for `min_silence_ms` (100–2000) and `threshold` (0.1–0.9).

### 2a.2 — Word-level timestamps + multi-format output

Add `word_timestamps=True` as a setting (default OFF, because it's slower). When ON:

- The JSON output gains a `words` field per segment (list of `{start, end, word, probability}`)
- A new VTT karaoke output (`<base>.karaoke.vtt`) is written

Refactor SRT writing out of `core/transcriber.transcribe`. New `core/writers/` package:

```
core/writers/
├── __init__.py
├── base.py          # protocol: write(segments, audio_path) -> str
├── srt.py
├── vtt.py
├── tsv.py
├── txt.py
├── json_writer.py
└── lrc.py
```

Each writer is a pure function taking a list of segment dicts (with optional `words`) and returning the file body as a string. The caller writes to disk. Steal logic from `openai-whisper`'s `whisper/utils.py` (MIT) for the line-breaking conventions. Unit-test each writer with a 3-segment fixture.

Settings: `"output_formats": ["srt", "json"]` (default). UI: a checkbox group on the Transcribe tab.

### 2a.3 — Language detection display

Capture `info.language` and `info.language_probability` from the `transcribe` return. Emit a new worker event `{"event": "language_detected", "language": "fa", "probability": 0.97}`. The App shows `Detected: Persian (97%)` next to the queue tree row for that task.

### 2a.4 — BatchedInferencePipeline for GPU

If `device == "cuda"`, wrap `MODEL` in `faster_whisper.BatchedInferencePipeline(model=MODEL)`. Setting `"batch_size": 16` (default), exposed in an Advanced settings dialog.

### 2a.5 — Robust device detection via CTranslate2

Replace `detect_device` with the version that uses `ctranslate2.contains_cuda_device()` and `ctranslate2.get_supported_compute_types("cuda")`. Drop torch as a hard runtime dep — it's still allowed transitively if the user has it, but not required for inference.

### 2a.6 — Initial prompt and hotwords (settings only, no UI yet — Phase 2b)

Stub the API: `transcribe` accepts an optional `initial_prompt` and `hotwords`. UI for these comes in Phase 2b, but the plumbing must be in place.

### 2a.7 — Real audio test fixtures

Create `tests/fixtures/audio/`:

- `silent_1s.wav` — 16-bit PCM, 16 kHz mono, 1 second of silence (generate with `numpy + wave` in a one-shot script; commit the WAV — it's ~32 KB)
- `tone_440hz_2s.wav` — same format, 2 s of 440 Hz sine wave (smoke that audio decoding works)
- `tts_hello_world.wav` — optional, if you can generate it with `pyttsx3` or a small fixture you ship. If generating fails, skip and document

Test:
- `tests/test_transcribe_smoke.py` — load `tiny.en` model (39 MB download, cache in `user_cache_dir / "models-test"`), transcribe `silent_1s.wav`, assert no crash and `info.language` is set. Skip if `tiny.en` cannot be downloaded (no network).
- For VAD: transcribe `silent_1s.wav` with `vad_filter=True` and assert the result has zero or one segment (VAD should suppress all silence).

### 2a.8 — Phase 2a acceptance

`docs/PHASE_2A_ACCEPTANCE.md`:

| ID | What |
|---|---|
| 2A-T1 | `transcribe` returns segments with VAD applied by default |
| 2A-T2 | `transcribe` with `word_timestamps=True` returns segments whose `.words` is non-empty for non-silent audio |
| 2A-T3 | Each writer in `core/writers/` produces a valid file body (SRT parses with `pysrt`, VTT starts with `WEBVTT`, JSON is a list of dicts, etc.) |
| 2A-T4 | UI shows `Detected: <lang> (<pct>%)` after a transcribe finishes |
| 2A-T5 | `BatchedInferencePipeline` is used when `device=="cuda"` (mock-test the construction) |
| 2A-T6 | `detect_device` works without torch installed (uninstall in a tox env and rerun) |
| 2A-T7 | Real audio smoke test: load tiny.en, transcribe silent_1s.wav, no crash |
| 2A-T8 | All Phase 0 + 1a + 1b + 2-oTranscribe tests still pass |

### 2a.9 — Compile checkpoint (light)

Same as 1b.6.

### 2a.10 — Push checkpoint

Append to SESSION_LOG, CHANGELOG, ROADMAP. Push.

---

## Phase 3a — yt-dlp masterpiece

Goal: end-to-end killer flow. The user pastes a YouTube URL, the app downloads it, **automatically transcribes the audio** with the right language hint from yt-dlp metadata, and writes SRT/VTT next to the media file.

### 3a.1 — `--progress-template "%(progress)j"`

Replace the brittle `[download] N%` regex with one JSON line per progress event. The download service parses each line with `json.loads`. Fields available: `downloaded_bytes`, `total_bytes`, `speed`, `eta`, `filename`.

### 3a.2 — SQLite history

New module `core/history.py`. SQLite at `user_data_dir() / "history.db"`. Schema:

```sql
CREATE TABLE IF NOT EXISTS downloads (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT,
  folder TEXT,
  format_label TEXT,
  status TEXT,
  started_at INTEGER,
  finished_at INTEGER,
  output_paths TEXT,
  detected_language TEXT,
  error TEXT
);
CREATE TABLE IF NOT EXISTS transcriptions (
  id INTEGER PRIMARY KEY,
  file_path TEXT NOT NULL,
  model TEXT,
  status TEXT,
  started_at INTEGER,
  finished_at INTEGER,
  duration_seconds REAL,
  language TEXT,
  output_paths TEXT,
  error TEXT
);
```

On app start, mark any `running` or `waiting` row as `interrupted`. The queue tabs read from SQLite on start and re-display old jobs.

### 3a.3 — SponsorBlock

Settings: `"sponsorblock_categories": []` (e.g. `["sponsor", "intro", "outro", "interaction"]`). When non-empty, append `--sponsorblock-remove sponsor,intro,outro` to the yt-dlp media command. UI: a checkbox group in a `Download Settings` dialog accessible from the Download Videos tab.

### 3a.4 — Auto-transcribe-after-download (the killer feature)

Add `auto_transcribe_after_download` setting (default OFF). When ON:

- After a download's media phase succeeds, identify the saved media file (capture the path during the `--newline` output of `yt-dlp`)
- Build a `TranscriptionTask(file_path=saved_path, language=task.detected_language)`
- Push it to the transcription queue
- The user sees the new row appear in the Transcription Queue tab automatically

Settings UI on the Download Videos tab: a checkbox `Transcribe after download`. When checked, downloads emit a status line `→ Queued for transcription` on completion.

### 3a.5 — UI changes

- Right-click history rows on either queue tab → `Open output folder`, `Remove from history`, `Re-run`
- A `Statistics` menu item → small dialog showing total downloads, total transcription minutes, top languages

### 3a.6 — Tests

- `tests/test_history_db.py` — open/close/insert/query, migrations from empty
- `tests/test_progress_template_parser.py` — JSON line parsing, edge cases (missing fields, non-JSON garbage from yt-dlp)
- `tests/test_auto_transcribe_wiring.py` — mock yt-dlp completion event, assert the matching `TranscriptionTask` is enqueued with the right path and language

### 3a.7 — Phase 3a acceptance

`docs/PHASE_3A_ACCEPTANCE.md`:

| ID | What |
|---|---|
| 3A-T1 | `parse_progress_line` handles `{"downloaded_bytes":1234,"total_bytes":5678,"speed":100,"eta":45}` and returns the right dict |
| 3A-T2 | `core.history.HistoryDB` creates tables on first open, idempotent on second open |
| 3A-T3 | A finished download writes a row to `downloads` with non-null `output_paths` |
| 3A-T4 | Auto-transcribe wiring: a `download_event("done")` enqueues a `TranscriptionTask` with `language` set from `detected_language` |
| 3A-T5 | SponsorBlock flag is appended to the yt-dlp argv when `sponsorblock_categories` is non-empty |
| 3A-T6 | UI: after a successful download with auto-transcribe ON, the Transcription Queue tab has one new row |
| 3A-T7 | All prior acceptance tests still pass |

### 3a.8 — Push checkpoint

Same as 2a.10.

---

## Final compile + smoke (after 3a passes)

This is the "compile test" the user explicitly asked for. Mandatory.

### Compile

Create `whisper_project.spec` (PyInstaller, deterministic, committed) in the repo root:

```python
# whisper_project.spec
# Run: pyinstaller --noconfirm whisper_project.spec
a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('bin', 'bin'),
        # sv_ttk theme assets are auto-detected by hooks
    ],
    hiddenimports=['app', 'app.app', 'core', 'core.logging_setup',
                   'core.integrations.otranscribe',
                   'core.writers.srt', 'core.writers.vtt',
                   'core.writers.json_writer', 'core.writers.tsv',
                   'core.writers.txt', 'core.writers.lrc'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='WhisperProject', console=False, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, name='WhisperProject')
```

```bash
pip install pyinstaller
pyinstaller --noconfirm whisper_project.spec
```

Output: `dist/WhisperProject/WhisperProject.exe`.

### Smoke test the binary

```bash
# Launch the built exe; wait 5 seconds; assert it's still running; kill it; check exit
python - <<'PY'
import subprocess, time, sys, os
p = subprocess.Popen([r"dist\WhisperProject\WhisperProject.exe"])
time.sleep(5)
if p.poll() is not None:
    print(f"BUILD_SMOKE_FAIL: process exited within 5 s, code={p.returncode}")
    sys.exit(1)
p.terminate()
try: p.wait(timeout=10)
except subprocess.TimeoutExpired: p.kill()
print("BUILD_SMOKE_PASS")
PY
```

Pass criterion: stdout contains `BUILD_SMOKE_PASS`.

If the smoke fails, mark Phase 3a `COMPLETE_BUT_BUILD_BROKEN` in the report, do NOT push the final commit if it touches the spec file, document the failure in `docs/AUDIT.md` as a new finding.

### Document the build

- `docs/BUILD.md` — how to build, where the binary lives, known PyInstaller hook issues
- `.gitignore` — add `build/` and `dist/` and `*.spec.bak` (keep the spec file)
- `docs/CHANGELOG.md` — entry for the spec file

---

## Final report

When Phase 1b + Phase 2a + Phase 3a all pass acceptance AND the compile smoke passes:

```bash
git push origin master
```

Then emit exactly one JSON object. No prose around it.

```json
{
  "session_id": "session-5",
  "branch": "master",
  "started_from": "985ffa6",
  "ended_at": "<sha>",
  "phases": {
    "phase_1b":          {"overall": "ACCEPTED", "commits": [...], "tests": {...}},
    "phase_2a":          {"overall": "ACCEPTED", "commits": [...], "tests": {...}},
    "phase_3a":          {"overall": "ACCEPTED", "commits": [...], "tests": {...}},
    "phase_0_replay":    {"overall": "ACCEPTED"},
    "phase_1a_replay":   {"overall": "ACCEPTED"},
    "phase_2_otranscribe_replay": {"overall": "ACCEPTED"}
  },
  "compile": {"status": "ok", "exe": "dist/WhisperProject/WhisperProject.exe", "smoke": "BUILD_SMOKE_PASS"},
  "push": {"status": "ok", "remote": "origin/master", "head": "<sha>"},
  "metrics": {
    "commits_added": <int>,
    "tests_added": <int>,
    "lines_added": <int>,
    "lines_removed": <int>,
    "coverage_core_pct": <float>
  }
}
```

If anything fails, replace the relevant `"ACCEPTED"` with `"REJECTED"` plus an `"evidence"` field, set `"push": {"status": "skipped_due_to_failure"}` for unpushed phases, and exit.

---

## Constraints (recap)

- **Single branch `master`.** No new branches. No rebases. No amends. No force-pushes.
- **One commit per logical unit.** Commit messages start with `Phase NX.Y:`.
- **Push at every phase boundary.** Use the host credential helper; never embed tokens.
- **No silent skips.** If something is impossible (e.g. `tiny.en` model can't download), document in a new `docs/PHASE_NEXT_BLOCKED.md` file and continue with the parts that work.
- **Re-run all prior acceptance suites** at every phase boundary. Fix regressions in a `Phase NX.Y hotfix:` commit before moving on.
- **Append to `docs/SESSION_LOG.md`** at every phase boundary. Append-only.
- **AUDIT updates.** If your refactor uncovers a CRITICAL or HIGH item not in the existing AUDIT, add a row to `docs/AUDIT.md` and fix it. Mention it in the JSON report.
- **No new heavy runtime deps** beyond: `responses` (dev only), `pyinstaller` (dev only), `sentry-sdk` (optional, off unless `SENTRY_DSN` env set).
- **PyInstaller `--onedir`**, not `--onefile`. False-positive antivirus rate is dramatically lower on `--onedir`.
- **Don't touch the worker subprocess JSON protocol.** Add fields, never remove or rename.

---

## Known traps from prior sessions

1. **`platformdirs` with `appauthor=None`** double-nests the folder on Windows (`...\WhisperProject\WhisperProject`). Phase 1a chose `APP_AUTHOR = False`. Keep it.
2. **The worker emits JSON on stdout.** Never `print()` anything else there. Logging in the worker must go to stderr or to a file (Phase 1a `setup_logging` already does this).
3. **Tk is single-threaded.** Only `poll_*` methods on the App may touch widgets. Services produce events; the App polls.
4. **Cancel must be safe to call multiple times** and from the Tk main thread only.
5. **oTranscribe's `text` HTML must stay single-line** (no literal `\n` inside the JSON string). The integration tests in Phase 2-oTranscribe already enforce this — don't break them.
6. **`config.json` is now in `%LOCALAPPDATA%\WhisperProject\`** — not next to the executable. References to `os.path.join(BASE, "config.json")` in Phase 0 code may still exist; the Phase 1a migration handled most. If you find any survivor, fix it.
7. **`ffprobe`/`ffmpeg`/`yt-dlp` live in `bin/`.** Always resolve through `bundled_binary("...")`. Tests must not rely on system PATH.
8. **The bundled binaries are gitignored.** PyInstaller must explicitly include `bin/` via `datas` in the spec file (already in the spec template above).
9. **`sv-ttk` ships its theme files separately.** PyInstaller usually picks them up via the built-in hook. If the built exe launches with default Tk look, you need to add `('<sv_ttk_dir>', 'sv_ttk')` to `datas`.
10. **Python 3.14 is what the user runs.** Avoid `pip install` of packages that have no 3.14 wheel — verify before committing them to `pyproject.toml`.

---

## Pointers

- `docs/SESSION_LOG.md` — history. Append your session's narrative.
- `docs/PHASE_0_ACCEPTANCE.md` — re-run.
- `docs/PHASE_1_ACCEPTANCE.md` — re-run.
- `docs/integrations/otranscribe-acceptance.md` — re-run.
- `docs/PHASE_1B_ACCEPTANCE.md` — you author this.
- `docs/PHASE_2A_ACCEPTANCE.md` — you author this.
- `docs/PHASE_3A_ACCEPTANCE.md` — you author this.
- `docs/BUILD.md` — you author this when you finish the compile step.
- `whisper_project.spec` — you author this in the repo root.

After the final report and `git push`, exit. The user does not need to be prompted; you have committed and pushed.
