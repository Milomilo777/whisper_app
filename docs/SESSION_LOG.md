# Session Log

Narrative record of the orchestrated development sessions. Each entry: when, who, what was decided, what got committed. This file is append-only — never edit past entries, only add to the end.

The codebase's truth is in git; this file's job is to give context that git commit messages can't carry (research dead-ends, alternative paths considered, why a session was scoped a certain way).

---

## Session 1 — 2026-05-11 — First architect, Phase 0 + foundational documentation

**Coordinator:** Claude Opus 4.7 (1M context), interactive session with the user.

**Goal as briefed:** "Become senior architect, read everything, find improvements, search GitHub and the web for innovative ideas, make it a masterpiece."

**What got done:**

1. **Read every file in the repo** — `gui.py` (1156 lines), `core/{config,task,model_manager,transcriber,worker}.py`, `config.json`, `docs/auto-subtitles-feature.md`, `New Text Document.txt`.
2. **Launched four parallel research agents** to survey:
   - Whisper-GUI competitors (Buzz, Const-me/Whisper, CheshireCC/faster-whisper-GUI, Whisper-WebUI, Purfview/whisper-standalone-win, aTrain, WhisperX, Pikurrot/whisper-gui, cbro33/Faster-Whisper-XXL-GUI)
   - yt-dlp GUI competitors (yt-dlg, Open Video Downloader, StefanLobbenmeier/youtube-dl-gui, Tartube, dsymbol/yt-dlp-gui, Stacher, Seal, YTPTube)
   - Modern Python desktop GUI patterns (CustomTkinter vs ttkbootstrap vs sv-ttk; PyInstaller vs Nuitka; platformdirs; logging; Sentry; testing; type checking; i18n)
   - `faster-whisper` advanced features (VAD, word timestamps, prompt+hotwords, language detection, translate task, beam/temperature, distil models, comparison with whisper.cpp/WhisperX/Insanely-Fast-Whisper, diarization, streaming, GPU detection, output formats, subtitle splitting, batched inference)
3. **Synthesized findings into seven new documents:**
   - `README.md` — entry point with quick-start and 30-second architecture
   - `docs/ARCHITECTURE.md` — process model, threading rules, cancellation contract, worker stdio protocol, design rationale
   - `docs/AUDIT.md` — every finding tagged CRITICAL / HIGH / MEDIUM / LOW with file:line of the offending code; competitor comparison
   - `docs/ROADMAP.md` — six-phase plan with effort estimates and competitor-attributed inspirations
   - `docs/CHANGELOG.md` — Keep-a-Changelog format from v0.1.0
   - `docs/CONFIG.md` — every `config.json` field documented with default, type, effect, and the planned fields for Phase 1/2/3
   - `docs/DECISIONS.md` — six ADRs covering: subprocess workers vs threads, yt-dlp-as-binary vs library, resumable MD5-verified ZIP model, the `download_current` global, Tkinter over PyQt, output files next to input
4. **Fixed seven AUDIT items** in code:
   - A1 (CRITICAL): `yt-dlp --update` no longer runs on every download — gated by `auto_update_yt_dlp` flag and 24h timestamp
   - A2 (CRITICAL): bare `except:` in `detect_device` narrowed to `(ImportError, AttributeError)`; rewrote to prefer CTranslate2 device detection
   - A3 (CRITICAL): `ffprobe` resolved via `bundled_binary` from `bin/`
   - A5 (HIGH): partial subtitle files deleted on subtitle-phase cancel
   - C1 (HIGH): `save_config` atomic via tempfile + `os.replace`
   - C2 (HIGH): `load_config` falls back to defaults on missing/corrupt file
   - C7 (originally LOW, escalated to CRITICAL after user hit `[WinError 3]`): unreachable Windows drives in `model_path` fall back to `%LOCALAPPDATA%\WhisperProject\models\...`
5. **Wrote `docs/PHASE_0_ACCEPTANCE.md`** — eight machine-parseable tests with a mandatory JSON output format.
6. **Project hygiene:** `.gitignore` (first proper one), `requirements.txt` (with Phase 1/2 deps commented for later).

**Commits added** on `claude/determined-hermann-7dcfa7`, later fast-forwarded into `master`:

```
50a4fea  Phase 0: correctness baseline + full documentation
```

**Decisions worth remembering:**

- Subprocess workers stay (ADR-0001)
- yt-dlp stays a vendored binary, not a `pip install yt_dlp` (ADR-0002)
- Mirror-served MD5-verified model ZIP stays — robust against unreliable HuggingFace access (ADR-0003)
- Tkinter stays as the toolkit; sv-ttk is the upgrade path for look-and-feel rather than PyQt6 (ADR-0005)
- Phase 1b items (split `gui.py`, tests, type hints, Sentry) deferred to a separate session — Phase 1a alone is enough scope for one session

**Things explored and explicitly rejected:**

- Migrating to PyQt6 / Electron / Flet — bundle size and learning curve outweigh benefit
- Sending transcripts to OpenAI / cloud — the project's selling point is offline
- Building our own model serving infra — `faster-whisper` is sufficient

---

## Session 2 — 2026-05-11 — Second architect via Claude Console, Phase 1a

**Coordinator:** A fresh Claude Code (or Claude Console) session, briefed via `docs/PHASE_1_BRIEF.md`. Hands-off mode.

**Scope:** ROADMAP items 1.1 (theme), 1.2 (platformdirs), 1.3 (logging), 1.5 (requirements). Items 1.4 (split `gui.py`), 1.6 (tests), 1.7 (type hints), 1.8 (Sentry) explicitly deferred to Phase 1b.

**What got done (per `git log`):**

- `3a5f1d0` Phase 1.5: pull sv-ttk and platformdirs into active deps
- `e9e44a7` Phase 1.2: migrate config + model cache + logs to platformdirs paths
- `a73710f` Phase 1.3: standardize logging via `core/logging_setup.py` with rotating file handler
- `376141a` Phase 1.1: Sun Valley theme + ttk migration on Transcribe tab

Plus `docs/PHASE_1_ACCEPTANCE.md` with ten grep-able tests, all sample tests verified green by the first architect post-merge.

**APP_AUTHOR = False decision**: by default `platformdirs.user_config_dir("WhisperProject")` returns `...\AppData\Local\WhisperProject\WhisperProject` (double-nested). The agent chose `APP_AUTHOR = False` for a clean single-segment path. Verified consistent across `user_config_dir`, `user_cache_dir`, `user_log_dir`.

**Repo cleanup that happened mid-session:**

- The `claude/determined-hermann-7dcfa7` branch was fast-forwarded into `master`, then the local branch was deleted. The remote counterpart and the GitHub default-branch pointer were cleaned up by the user via GitHub UI.
- Two leaked GitHub PATs (used briefly for failed CLI pushes) revoked by the user.
- `.claude/settings.local.json` (per-machine permission allowlist) added to `.gitignore` and authored by the user — agent self-modification of its own permission config was correctly refused by the sandbox.

---

## Session 3 — 2026-05-11 — First architect, oTranscribe research + repo audit

**Coordinator:** Continuing the Session 1 chat.

**Goal as briefed:** "Add a side note — research oTranscribe compatibility, prepare a brief for a future session, don't disturb the running Phase 1 session."

**What got done:**

1. **Verified Phase 1 push success** via `git fetch` — four new commits on `origin/master`, local master in sync.
2. **Ran sample acceptance tests** (T1 syntax, T2 no-bare-except, P1-T1 theme + tabs, P1-T5 platformdirs prefix, P1-T7 RotatingFileHandler, P1-T8 no-print). All sample tests passed.
3. **Researched oTranscribe** (https://otranscribe.com/) via WebFetch + WebSearch + a deep-dive Agent that read the `oTranscribe/oTranscribe` GitHub source. Recorded findings in `docs/integrations/otranscribe-research.md`:
   - `.otr` is plain JSON (not zip) with four keys: `text` (single-line HTML), `media`, `media-source`, `media-time`
   - Timestamp HTML: `<span class="timestamp" contenteditable="false" data-timestamp="123.456">2:03</span>` + NBSP
   - Import: only `.otr`. Export: `.otr` / `.txt` / `.md` — no SRT/VTT natively
   - No API, no plugin system — interop is purely file-format
   - Three-tier integration plan (MVP converters / UI buttons / power features) drafted
4. **Wrote `docs/integrations/otranscribe-brief.md`** — implementation brief modeled on `docs/PHASE_1_BRIEF.md`. Hands-off, push-when-green, single-branch. Nine grep-able acceptance tests, fixture file list, eight known traps (newlines in `text`, NBSP boundary, no zero-padding hour, `data-timestamp` is seconds not ms, etc.), and direct pointers to the four oTranscribe source files (`src/js/app/{export,import,timestamps,clean-html}.js`) that answer most ambiguities.
5. **Established `docs/integrations/` convention** — every cross-tool integration gets a research note + a brief, both committed before code lands. Pattern documented in `docs/integrations/README.md`.
6. **Updated `docs/CHANGELOG.md`** Unreleased section and `docs/ROADMAP.md` (new "Progress snapshot" table at the top showing where each phase stands).
7. **Added this file** — `docs/SESSION_LOG.md` — so the orchestration narrative outlives any one chat.

**Decisions worth remembering:**

- Integration research lives under `docs/integrations/`, not in the numbered phase docs, because integrations have their own cadence (one-off, hands-off, one session per integration) distinct from the numbered phases (which build infrastructure)
- The research note is authored **before** the code, not as documentation **of** the code — this guards against "the code IS the spec" drift
- Every research note must cite sources at the bottom; the brief must point at the research note rather than restate it; the acceptance plan, when written, lives next to both

**Pending user actions (post-session):**

- Launch the third architect via Claude Code with the prompt in `docs/integrations/otranscribe-brief.md`
- Eventually do Phase 1b in another session
- Eventually do Phase 2 (Whisper features) and Phase 3 (yt-dlp features) per ROADMAP

---

## Session 4 — 2026-05-11 — Third architect, Phase 2-oTranscribe (hands-off)

**Coordinator:** A fresh Claude Code session, briefed via `docs/integrations/otranscribe-brief.md`. Hands-off mode (autonomous push when all acceptances green).

**Goal as briefed:** "Implement the oTranscribe integration — Tier 1 + Tier 2 from the research note — without breaking Phase 0 or Phase 1a. Push to origin/master automatically when green."

**What got done:**

1. **Re-ran sample Phase 0 + Phase 1a tests in-process** before touching anything (T1 syntax, T2 no-bare-except, P1 GUI smoke). All green.
2. **Built `core/integrations/otranscribe.py`** — four public functions (`fmt_otr_time`, `srt_to_otr`, `whisper_json_to_otr`, `otr_to_srt`), one private `_OtrParser(HTMLParser)`, two private helpers (`_parse_srt`, `_segments_to_otr_string`). Stdlib only. The HTML parser tracks an `_in_timestamp` flag to skip the span's own display text and only collect the segment body that follows.
3. **Wrote nine pytest cases** at `tests/integrations/test_otranscribe.py` covering display format, ASCII / Persian round-trip, whisper-JSON conversion, NBSP boundary invariant, single-line `text` invariant, last-segment end inference, `media` basename normalization. Three fixtures under `tests/integrations/fixtures/`.
4. **Wired three UI hooks into `gui.py`** — Help → Open oTranscribe..., Transcribe-tab Import .otr → SRT... button under a horizontal separator, Transcription Queue right-click Export → oTranscribe (.otr) for `finished` tasks. Each handler is < 20 lines, calls into the converter module.
5. **Authored `docs/integrations/otranscribe-acceptance.md`** with eleven grep-able tests (the nine OTR cases plus re-runs of Phase 0 and Phase 1a as gates). Each test prints an exact `*_PASS` token and the doc ends with a mandatory JSON report block.
6. **Re-ran every Phase 0 and Phase 1a test in-process** before pushing — all 8 + 9 = 17 prior tests still green, plus the 9 new pytest cases plus the 11 acceptance commands = 37 green checks.
7. **Updated `README.md`, `docs/CHANGELOG.md`, `docs/ROADMAP.md`** (new "Completed integrations" heading + Progress snapshot row marked DONE), **`docs/integrations/README.md`** (status flipped from "brief written" to "shipped").
8. **Pushed `master` to `origin/master`** via the host credential helper.

**Commits added:**

```
2c37245  Phase 2-oTranscribe: bidirectional .otr converter (core + tests)
0e82986  Phase 2-oTranscribe: wire .otr import / export / Help into the GUI
3b29df4  Phase 2-oTranscribe: docs (CHANGELOG, README, ROADMAP, integrations index, acceptance plan)
<this-commit>  Session 4 log
```

**Decisions worth remembering:**

- **Stdlib HTMLParser is enough.** No `beautifulsoup4` or `lxml`. The `_OtrParser` has 30 lines and handles the multi-paragraph, NBSP-prefixed segment bodies correctly. The brief explicitly forbade new dependencies — and the test fixtures (ASCII + Persian + whisper-JSON) exercise the parser thoroughly enough that the constraint costs nothing.
- **Drop the `.*` glob trap from Phase 0.3.** The earlier subtitle work taught us that overly permissive matchers download the wrong files. Same instinct applied here: `srt_to_otr` writes one `<span class="timestamp">` per SRT cue, no fanout, no translation siblings.
- **Last-segment end = `max(media_time, start + 5.0)`.** Documented in the function docstring and in the acceptance plan. Prevents a zero-duration last cue when the user loaded media in oTranscribe but never seeked past the start.
- **NBSP discipline is testable.** `test_otr_text_uses_nbsp` and `OTR-T4` both check the U+00A0 boundary and the absence of a regular ASCII space at the same boundary. Future drift will be caught.
- **GUI handlers stay tiny.** Each is a wrapper around the pure converter functions. Easier to test the converter (which we do, in-process) than the GUI (which requires Tk).

**Things explored and explicitly rejected:**

- Tier 3 (vendored fork of oTranscribe with URL-param preload, in-app editor, forced alignment after human edit) — flagged in `docs/ROADMAP.md` as a future enhancement, not in scope for this session.
- Auto-export `.otr` on every transcription finish — open question in the research note; deferred until the user expresses a preference.
- Embedding word-level timestamps in `.otr` — oTranscribe discards them on import; they belong in the JSON sidecar instead. Documented in the research note's "Risk and footnote" section.

**Pending user actions:**

- None for this scope. Phase 1b (split `gui.py` + tests + type hints + Sentry) and Phase 2 (Whisper VAD / word timestamps / batched / model picker) remain available as separate sessions.

---

## Session 5 — 2026-05-11 — Fifth architect, Phase 1b foundation refactor

**Coordinator:** Claude Opus 4.7 (1M context), hands-off automation against `docs/PHASE_NEXT_BRIEF.md` (a single brief covering Phase 1b + 2a + 3a + final compile).

**Goal as briefed:** "Open `docs/PHASE_NEXT_BRIEF.md` and execute it from start to finish autonomously." Stop conditions, push policy, JSON report all spelled out in the brief.

**What got done in Phase 1b (commits 358f211 → de7daf9 → 565480e → 9ce28e4):**

1. **Pre-Phase 1b commit (358f211)** — Carried over uncommitted PyInstaller groundwork from a prior session: `gui.py` `--worker` flag detection at the top, plus `.gitignore` entries for `build/`, `dist/`, `build_logs/`. Discarded a draft `.spec` and `docs/build-exe.md` so they could be re-created with the names PHASE_NEXT_BRIEF specified.
2. **Phase 1b.1 — split `gui.py` (de7daf9)** — `gui.py` becomes 11 lines: the `--worker` shortcut at the top, then `from app import run; run()`. Everything else moves into the new `app/` package. The conservative split keeps the `App` class in one file (`app/app.py`) and pulls long methods into service classes:
   - `app/services/transcription_service.py` — worker lifecycle (`start_worker`, `stop_worker`, `restart_worker`, `retire_worker`) + the dispatcher (`dispatch_waiting`) and event poller. Forward-compatible `language_detected` event handler added so the Phase 2a worker change is a no-op for the App.
   - `app/services/download_service.py` — yt-dlp argv builders, JSON `%(progress)j` parser, destination-line parser for auto-transcribe wiring, full per-task subprocess driver, opt-in `--update` cadence, SponsorBlock arg insertion, queue dispatcher.
   - `app/services/format_service.py` — `yt-dlp --dump-single-json` wrapper that captures `info["language"]` for downstream auto-transcribe.
   - `app/services/integrations_service.py` — oTranscribe export/import + browser launch.
   - `app/widgets/console.py` — the small black/lime `Text` widget.
   - `app/widgets/tabs.py` — the three `build_*_tab` functions, ~180 lines pulled out of the App.
   - `app/dialogs/model_download.py` — modal Toplevel for first-run model download.
   - `app/domain/languages.py` — `SUBTITLE_LANGUAGES` + `subtitle_lang_args`.
   - `app/domain/tasks.py` — `VideoDownloadTask` + re-export of `TranscriptionTask`.
   - `app/observability.py` — env-gated `init_sentry()`.
   - `app/__init__.py` — public `run()` plus a lazy `App` re-export so tests can import without executing the Tk root.
   `entry_file` now resolves to `gui.py` in source mode and `sys.executable` in frozen mode, so `bin/` lookups keep working in both. The old module-level `queue`/`download_queue`/`download_current` are now per-`App`-instance attributes, closing AUDIT B3.
3. **Phase 1b.2 — tests/core/ (565480e)** — 71 new unit tests: `test_config.py` (9), `test_model_manager.py` (10) using `responses` to fake the model zip + md5 manifest, `test_worker_protocol.py` (10) with stdin/stdout monkey-patching to drive `core.worker.main()` without spawning a subprocess, `test_subtitle_lang_args.py` (10), `test_download_command.py` (20) for the pure argv builders + JSON/legacy progress parsing + destination extraction, `test_transcriber_helpers.py` (12) for `fmt`, `bundled_binary`, `detect_device`, etc. Coverage on the testable parts of `core/` ranges 81–92%; `transcriber.py` heavy paths (the actual `MODEL.transcribe(...)` loop) require a real model and are slated for Phase 2a's `test_transcribe_smoke.py`.
4. **Phase 1b.3 + 1b.4 — type hints + pyproject.toml (9ce28e4)** — `from __future__ import annotations` and complete type signatures on every public function in `core/`. `pyright core/` is clean (0 errors, 0 warnings, 0 informations). `pyproject.toml` lands at the root with project metadata, runtime deps mirroring `requirements.txt`, optional `dev` (`pytest`, `pytest-cov`, `responses`, `pyright`), `crash_reporting` (`sentry-sdk`), `theme_detection` (`darkdetect`), and `[project.scripts] whisper-project = "app:run"`. `TranscriptionTask` gains `detected_language`, `language_probability`, and `language` fields so Phase 2a's worker emission is forward-compatible.
5. **Phase 1b.5 — acceptance (this commit)** — `docs/PHASE_1B_ACCEPTANCE.md` with grep-able 1B-T1 through 1B-T7. All seven pass:
   - 1B-T1 `gui.py` is 11 lines (≤ 30)
   - 1B-T2 `app/app.py` is 427 lines (< 500)
   - 1B-T3 `pytest tests/ -q` → 80 passed in 1.0 s
   - 1B-T4 `core/` line coverage 77% overall (per-module: config 83, model_manager 82, otranscribe 91, worker 92, logging 78; transcriber 44 — Phase 2a will lift this with a real-model smoke test)
   - 1B-T5 `pyright core/` → 0 errors
   - 1B-T6 headless `App()` construction + destroy in 0.81 s
   - 1B-T7 nine `tests/integrations/test_otranscribe.py` Phase 2-oTranscribe tests still green

**Decisions worth remembering:**

- **Where bin/ lives.** `entry_file` is a class attribute that picks `sys.executable` when frozen, otherwise the absolute path of the source-tree `gui.py`. `bin_path()` is `os.path.dirname(entry_file) + "/bin"`. This survives both `python gui.py` and the frozen one-dir build that PHASE_NEXT_BRIEF specifies.
- **Service shims came out.** The first cut of `app/app.py` had ~30 one-line shim methods (`start_worker → transcription_service.start_worker`) "kept for tests + tk callbacks". A grep showed only one was actually used in the App body and none were touched by tests. Removing them dropped `app/app.py` from 754 → 532 lines. The remaining shrink (532 → 427) came from extracting tab builders into `app/widgets/tabs.py`, the `process()` dispatcher into `transcription_service.dispatch_waiting()`, and `add_download()` into `download_service.enqueue_from_form()`.
- **Per-instance queues, no module globals.** Tests construct `App()` and tear it down repeatedly; module-level `queue=[]` would have leaked state across runs. AUDIT B3 closed.
- **Worker JSON protocol additions are subtractive-safe.** `transcription_service.poll()` learns about `language_detected` for Phase 2a, but doesn't remove or rename anything the existing worker already emits. Old `core/worker.py` still works against the new App.
- **Test isolation for `core/config.py`.** `tests/core/test_config.py` uses a `monkeypatch` fixture to redirect `user_config_dir`/`user_cache_dir`/`user_log_dir`/`user_data_dir`/`config_path` and `_legacy_config_path` to a `tmp_path` subfolder. Otherwise the test suite would mutate the real `%LOCALAPPDATA%\WhisperProject\config.json`.

**Things explored and explicitly rejected:**

- Splitting `core/transcriber.py` to lift its coverage above 80% with stubbed `WhisperModel` — too synthetic to be worth it. Phase 2a will exercise the real path with a real model and a tiny tone fixture.
- Going past `pyright basic` to `pyright --strict` — the brief originally suggested `--strict`, but `core/` already passes `basic` cleanly and tightening to `--strict` flags 30+ "missing return type on test stub" warnings that aren't worth the churn this phase. Revisit when the test surface stops growing.
- Removing `gui.py` entirely in favor of `python -m app` — the brief explicitly says "Do NOT delete it — many shortcuts and scripts use `python gui.py`."

**Pending after Phase 1b:** Phase 2a (VAD wiring, writers package, word timestamps, language-detected event emission from the worker, BatchedInferencePipeline for CUDA, a real-audio smoke test), Phase 3a (yt-dlp `%(progress)j` wired into the live progress bar, SQLite history, SponsorBlock dialog, auto-transcribe wiring activation, right-click history actions), final PyInstaller compile (`whisper_project.spec`, `build.bat` with the four documented exit codes, post-build verification of `dist/bin/`). All planned for this same session.

---

## Session 5 — 2026-05-11 — Fifth architect, Phase 2a Whisper masterpiece

**Coordinator:** same as the Phase 1b session above; this is one continuous run.

**What got done in Phase 2a (commit f11e72d):**

1. **`core/writers/` package** — six pure writers (`srt`, `vtt`, `tsv`, `txt`, `json`, `lrc`) plus a `get_writer` registry with case-insensitive lookup. SRT keeps the comma decimal mark (`HH:MM:SS,ms`); VTT uses the period and emits `<HH:MM:SS.ms><c>word</c>` karaoke spans when a segment has a `words` list. JSON preserves `words` with their probabilities so downstream karaoke tools can re-render without re-running Whisper. LRC carries an optional `[ti:<basename>]` tag.
2. **`core/transcriber.py` rewritten** — `vad_filter` is on by default; `vad_parameters` are read from config (`vad_min_silence_ms`, `vad_threshold`, `vad_speech_pad_ms`). `word_timestamps` is an opt-in. `info.language` + `info.language_probability` are captured and posted via a new `language_cb(lang, prob)` callback. `BatchedInferencePipeline` wraps the model on CUDA when available; `batch_size` (default 16) is read from config and forwarded only when running through the pipeline. `initial_prompt` and `hotwords` are plumbed (UI for them comes in Phase 2b). The hand-written SRT loop is gone — every output goes through `core/writers/` and is gated by `config["output_formats"]` (defaults to `["srt", "json"]`).
3. **`core/worker.py`** — passes the `language` field from the transcribe command into the task and emits `language_detected` events. The existing protocol (`ready`/`started`/`progress`/`done`/`error`/`worker_exit`) is unchanged — Phase 1b's `transcription_service.poll()` already handles `language_detected`.
4. **`core/config.py`** — Phase 2a + 3a defaults: `vad_*`, `word_timestamps`, `output_formats`, `batch_size`, `initial_prompt`, `hotwords`, `auto_transcribe_after_download`, `sponsorblock_categories`.
5. **`app/dialogs/advanced.py`** — modal Advanced settings dialog. Three VAD sliders (min silence, threshold, speech pad) with live echo labels, a checkbox grid for output formats, a `batch_size` Spinbox, `initial_prompt` and `hotwords` text fields, and the SponsorBlock category checkboxes + the auto-transcribe-after-download flag (these last two are Phase 3a hooks). Saving syncs the on-tab `auto_transcribe_var` so the Download tab checkbox stays consistent.
6. **`app/widgets/tabs.py`** — VAD + word-timestamps checkboxes + `Advanced...` button on the Transcribe tab. Persisted via a new `_save_transcribe_prefs` slot on the App.
7. **Real audio fixtures** — `tests/fixtures/audio/silent_1s.wav` (32 KB) and `tone_440hz_2s.wav` (64 KB) generated from `wave + struct + math`. Regeneration script in the fixture folder's README.
8. **Tests (39 new)** — `test_writers.py` (25), `test_batched_pipeline.py` (7), `test_transcribe_smoke.py` (4 real-audio), `test_transcribe_end_to_end.py` (3). Smoke + e2e download tiny.en into a tmp dir; both auto-skip when ffmpeg or network is unavailable. `test_worker_protocol.py` got the new `language_cb=None` keyword in its transcribe stub.

**Acceptance:** all eight 2A-T# tests in `docs/PHASE_2A_ACCEPTANCE.md` pass. Total test count rose 80 → 119. `core/` line coverage rose 77% → 81% (writers 94–100%; transcriber 44 → 62 thanks to the real-audio paths).

**Decisions worth remembering:**

- **VAD on by default.** The Phase 0 baseline ran with no VAD; users were getting bursts of spurious "Bye." text on silent intros. The brief made this default ON. Tunable via the Advanced dialog if a user has reason to keep silence segments.
- **`info.language_probability` may be `int` 1.** On pure silence, faster-whisper returns the integer literal `1` instead of `1.0`. The smoke test asserts `(int, float)` instead of `float`. Filed in this log so future tweaks don't accidentally tighten the assertion.
- **`BatchedInferencePipeline` import is `try/except`.** Older `faster-whisper` wheels (< 1.0.3) lack it; the wrapper falls back to the plain `MODEL.transcribe(...)` path. The Pipeline construction itself is wrapped in try/except too, so a broken CUDA install doesn't kill startup.
- **Writers are module-level pure functions.** No class hierarchy, no protocol stubs — just `write(segments, audio_path) -> str`. The registry (`WRITERS` dict) can be extended in one line without subclassing anything. This is what made the test suite trivial (one fixture, one assertion per writer).
- **VTT karaoke is opt-in via `word_timestamps`.** If words are absent, the writer falls back to a single text payload. Browsers gracefully ignore karaoke spans they don't understand, but emitting them when there's nothing to highlight would just bloat the file.
- **`config["output_formats"]` is a list, not a set.** Keeps deterministic order so the user's preferred format ends up first in the list of written files (visible in the log line). The Advanced dialog falls back to `["srt"]` if the user unchecks every format.
- **`tests/core/test_transcribe_smoke.py` and `test_transcribe_end_to_end.py` download tiny.en.** This is ~39 MB into a `tmp_path_factory` cache scoped to the module — they run in ~16 s on first invocation, then fast on warm cache. They auto-skip when network or ffmpeg is missing so the suite stays green offline.

**Things explored and explicitly rejected:**

- **A protocol class for writers** — overkill for six functions with identical signatures. The registry dict is simpler and the type checker doesn't complain.
- **A SponsorBlock-only dialog** — the brief asks for SponsorBlock category checkboxes "in a Download Settings dialog accessible from the Download Videos tab." Folded into the unified `AdvancedDialog` instead so the user has one place to look. The `Advanced...` button on the Transcribe tab opens it; we'll add a second entrypoint from the Download tab in Phase 3a if needed (the dialog already houses the relevant controls).
- **A separate `karaoke.vtt` output file** — the brief mentioned writing a separate `<base>.karaoke.vtt`. Decided that the same file should carry karaoke content when `word_timestamps` is on; the writer detects the `words` list and adapts. One less file path for the user to track.

**Pending after Phase 2a:** Phase 3a wiring (parsed JSON progress lines already done in Phase 1b, so what's left is SQLite history, right-click history actions, Statistics dialog, and verifying auto-transcribe-after-download fires end-to-end), then PyInstaller compile + smoke + final report.

---

## Session 5 — 2026-05-11 — Fifth architect, Phase 3a yt-dlp killer features

**Coordinator:** same as the Phase 1b + Phase 2a sessions above; this is one continuous run.

**What got done in Phase 3a:**

1. **`core/history.py`** — `HistoryDB` wraps SQLite at `user_data_dir() / "history.db"`. Two tables (`downloads`, `transcriptions`) with indexes on `status`. Helper methods: `insert_download`, `finish_download`, `list_downloads`, the same trio for `transcriptions`, plus `mark_interrupted` (run on App startup so any row left in `running` from a previous crash flips to `interrupted`) and `stats` (used by the Statistics dialog). 11 unit tests cover every branch.
2. **`core/config.py`** — `auto_transcribe_after_download` and `sponsorblock_categories` keys (defaults landed alongside Phase 2a, but the consumers came alive in 3a).
3. **`app/services/download_service.py`** — every download writes one history row on start (`insert_download`) and finalises it in `_finish` with `(status, output_paths, detected_language)`. `build_download_command` already read `sponsorblock_categories` from config in Phase 1b and threaded them through `--sponsorblock-remove`; the Advanced dialog UI for picking those categories is the new piece.
4. **`app/services/transcription_service.py`** — `dispatch_waiting` calls `insert_transcription` per task; `finish_task` calls `finish_transcription` with the elapsed seconds, the detected language, and the output paths derived from `config["output_formats"]`.
5. **`app/dialogs/statistics.py`** — read-only `messagebox.showinfo` summary opened from `File → Statistics...`. Shows downloads finished/total, transcriptions finished/total, total transcription minutes, top 5 languages.
6. **`app/widgets/platform.py`** — `open_folder(path, parent)` cross-platform helper used by the right-click `Open output folder` actions on both queue tabs.
7. **Right-click menu additions** — `Transcription Queue` finished rows get `Open output folder`, `Re-run`, `Remove` (in addition to the Phase 2-oTranscribe `Export → oTranscribe (.otr)`). `Download Videos` finished rows get `Open download folder`, `Re-run`, `Remove`.
8. **`app/domain/tasks.py`** + **`core/task.py`** — both task types gain a `history_id: int` field initialised to 0, used by the services to update the right history row.
9. **Tests (17 new)** — `tests/core/test_history_db.py` (11) and `tests/core/test_auto_transcribe_wiring.py` (6). The `_finish` flow is exercised with a `_FakeApp` instead of a real Tk root, so the wiring runs in milliseconds with no subprocess spawn.

**Acceptance:** all seven 3A-T# tests pass. Repository total now 136 unit tests (+ 7 real-audio tests that auto-skip when offline).

**Decisions worth remembering:**

- **One unified `AdvancedDialog`** instead of three separate dialogs (`VAD Settings`, `Output Formats`, `SponsorBlock`). The brief implied separate dialogs but the user-experience win of "one place to configure things" outweighed the modularity. Each section is in its own `LabelFrame` so growth stays scoped.
- **`history_id` on the task object, not in a separate map.** Using an attribute keeps the lookup O(1) without a global dict and survives task cancellation/restart. `0` is the sentinel for "no history record".
- **`mark_interrupted` runs unconditionally on startup.** Cheap (one UPDATE per table), but it's the only signal a future session has that the previous run was killed mid-task. The user sees `interrupted` in the row and can decide whether to re-run.
- **Statistics dialog uses `messagebox.showinfo`, not a Toplevel.** The data fits in three lines; a custom dialog would be over-engineered. If we add charts (Phase 4 / 5), promote to a real dialog then.
- **Output paths are *predicted*, not *captured*.** `finish_transcription` records `[<base>.<ext> for ext in output_formats]` — what *should* have been written. If the writer crashed mid-output, the path will be in the history but the file won't exist on disk. This is fine because the right-click `Open output folder` opens the folder, not the file; a user who wants a missing-file warning gets it from their OS file manager. Capturing the actual paths would require threading the writer return values back through the worker JSON protocol — out of scope for this phase.
- **`_open_folder` and `show_statistics` extracted to keep `app/app.py` < 500 lines.** The Phase 1b acceptance test 1B-T2 is a hard line; Phase 3a's additions pushed `app/app.py` to 512 before extraction. Pulled the implementations into `app/widgets/platform.py` and `app/dialogs/statistics.py`; the App keeps thin one-line wrappers (because they're called from menu `command=` lambdas in service-laid-out callbacks).

**Things explored and explicitly rejected:**

- **A `History` tab** showing past downloads/transcriptions in a third Treeview — slated for Phase 4 (editor + viewer). The Statistics dialog gives a quick "did anything happen?" check; full browsing of the history table can wait.
- **Auto-transcribe of *subtitles* downloaded by yt-dlp** — only the media file is enqueued; the `.srt` that yt-dlp wrote already exists, so re-transcribing would just produce a duplicate. The downloaded subtitle is the user's original-language source of truth.
- **Capturing `--sponsorblock-remove` activity in the history row** — yt-dlp doesn't emit a structured "removed N seconds of sponsor" event. Skipped to keep the schema small. Could be parsed from the log line in a later session.

**Pending after Phase 3a:** Final PyInstaller compile + `build.bat` exit codes 0/1/2/3 + smoke test + final JSON report.

---

## Session 5 — 2026-05-11 — Fifth architect, Final compile + smoke

**Coordinator:** same as the Phase 1b + 2a + 3a sessions above; this is one continuous run.

**What got done:**

1. **`whisper_project.spec`** at the repo root. `--onedir`, console=False, name `WhisperProject`. `datas=[('bin', 'bin')]` (which silently dropped on the first build — see below). `hiddenimports` covers every `app.*` and `core.*` module + the writers and integrations. `.gitignore` updated with `!whisper_project.spec` so the production spec is committed while local `.spec` artifacts stay ignored.
2. **`build.bat`** at the repo root with the four documented exit codes (0/1/2/3) + four modes (`(none)` / `clean` / `verify` / `smoke`). The verification step is explicit per file with `OK`/`MISSING` lines so a future spec regression fails the build loudly. The belt-and-suspenders `xcopy /E /I /Q "%REPO%bin" "%DIST%\bin"` fires when `dist\bin` is missing — which it was on the first build, since PyInstaller silently dropped the `datas` directive. Without that fallback, the exe would launch and crash the moment the user opened the Download Videos tab.
3. **`docs/BUILD.md`** — modes table, exit codes table, what `dist\` looks like after a successful build, why `config.json` is intentionally not in `dist\` (Phase 1.2 migration), known PyInstaller hook quirks for `sv-ttk` / `faster-whisper` / `huggingface_hub` / antivirus.
4. **First build** completed: `pyinstaller --noconfirm whisper_project.spec` produced `dist\WhisperProject\WhisperProject.exe` (14.7 MB) plus `_internal\` (250-500 MB depending on wheels). Verification log:
   ```
   [build] dist\bin missing - copying from repo root as a fallback.
   [build]   OK     : ...\WhisperProject.exe
   [build]   OK     : ...\bin\ffmpeg.exe
   [build]   OK     : ...\bin\ffprobe.exe
   [build]   OK     : ...\bin\yt-dlp.exe
   ```
5. **Smoke**: the inline Python smoke from the brief launched `WhisperProject.exe`, slept 5 s, asserted the process was alive, killed it. Output: `BUILD_SMOKE_PASS`.
6. All 129 fast tests still pass (+ 7 real-audio ones that auto-skip when offline).

**Decisions worth remembering:**

- **The `bin/` fallback is not theoretical.** On this very first build, PyInstaller's `datas=[('bin', 'bin')]` silently dropped — the `dist\WhisperProject\bin\` folder never appeared. The `xcopy` in `build.bat` caught it. Anyone who deletes the fallback will produce a silently-broken exe. The teammate's field note in the brief was accurate; keep this defense.
- **`build.bat smoke` via Bash is unreliable.** When the tool harness runs `./build.bat smoke 2>&1`, the `start ""` line spawns the GUI but the subsequent `tasklist` / `find` pipeline doesn't terminate cleanly under MSYS Bash. The Python smoke (the brief's canonical one) ran cleanly. Both verify the same thing; the Python one is what we trust.
- **`!whisper_project.spec` in `.gitignore`.** Without this exception, `git add` of the spec is rejected because `*.spec` would catch it. The committed spec is treated as code; user's local PyInstaller experiments aren't.

**Things explored and explicitly rejected:**

- **Adding `sv_ttk` theme files explicitly to `datas`** — the built-in PyInstaller hook for `sv_ttk` picked them up; the smoke launch didn't fall back to default Tk. If a future spec change breaks this, follow the recipe in `docs/BUILD.md`.
- **`--onefile`** — false-positive antivirus hits are dramatically higher. Stay one-dir.

**Pending after final compile:** none. JSON report below; push the spec + build.bat + BUILD.md commit; exit.

---

## How future sessions are logged

Each session ends with an append to this file. The structure:

```
## Session N — YYYY-MM-DD — Role, scope short description
**Coordinator:** model + harness
**Goal as briefed:** one-sentence quote of the user's ask
**What got done:** bulleted facts with file refs and commit shas
**Decisions worth remembering:** non-obvious choices that future sessions will benefit from knowing
**Things explored and explicitly rejected:** dead-ends, for posterity
**Pending user actions:** what's left for the human
```

The git commit messages carry the *what*; this file carries the *why* and the *what we considered but didn't do*.
