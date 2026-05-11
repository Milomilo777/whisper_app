# Roadmap

The prioritized plan for turning this from a working draft into a masterpiece. Every item names the source of inspiration (which competitor does this well), the rough effort, and the reason it matters. See `AUDIT.md` for the findings that justify the priorities; see `ARCHITECTURE.md` for the current shape.

Effort labels:

- **XS** — under an hour
- **S** — half a day
- **M** — one to three days
- **L** — a week
- **XL** — more than a week

---

## Progress snapshot

| Phase | Status | Notes |
|---|---|---|
| Phase 0 — correctness baseline + docs | **DONE** (`50a4fea`) | All CRITICAL and HIGH AUDIT items fixed; full docs suite published |
| Phase 1a — theme + platformdirs + logging | **DONE** (`376141a` + 3 prior) | `sv-ttk`, `%LOCALAPPDATA%` paths, RotatingFileHandler |
| Phase 1b — split gui.py + tests + type hints + Sentry | TODO | Separate session |
| Phase 2 — Whisper as serious transcription tool | TODO | VAD, word timestamps, batched inference, model picker, presets |
| Phase 2-oTranscribe — file-format compatibility | **DONE** (Session 4) | Tier 1 + Tier 2 shipped: bidirectional `.otr` converter, Export/Import UI, `Help → Open oTranscribe`. See [docs/integrations/otranscribe-acceptance.md](integrations/otranscribe-acceptance.md). Tier 3 (vendored fork, in-app editor, forced alignment) deferred — see Phase 5 backlog. |
| Phase 3 — yt-dlp as serious downloader | TODO | progress JSON, history DB, SponsorBlock, auto-transcribe-after-download |
| Phase 4 — editor and viewer | TODO | RTL Persian editor, bilingual side-by-side, subtitle linter |
| Phase 5 — power features | TODO | Diarization, vocal separation, live mic, REST, CLI, packaging |

Integration briefs live under `docs/integrations/` and follow a separate cadence from the numbered phases — each is a single hands-off session.

---

## Completed integrations

- **oTranscribe** (Session 4) — bidirectional `.otr` ↔ SRT round-trip, Export/Import UI, `Help → Open oTranscribe`. Reference: [research note](integrations/otranscribe-research.md), [implementation brief](integrations/otranscribe-brief.md), [acceptance plan](integrations/otranscribe-acceptance.md).

---

## Phase 0 — Critical fixes (do this week)

These are correctness or trust-breaking issues. The user gets a better product the moment they merge.

| # | Item | Source | Effort | Why |
|---|------|--------|--------|-----|
| 0.1 | Stop `yt-dlp --update` from blocking every download (AUDIT A1) | own audit | XS | One offline user = zero downloads |
| 0.2 | Replace bare `except:` in `transcriber.detect_device` with `except (ImportError, AttributeError):` (AUDIT A2) | own audit | XS | Ctrl+C currently disappears |
| 0.3 | Make `get_duration` use `bin/ffprobe.exe` instead of `ffprobe` on PATH (AUDIT A3) | own audit | XS | Hard-fails on clean machines |
| 0.4 | Atomic write for `config.json` (AUDIT C1) | own audit | XS | Crash-during-save = corrupt config |
| 0.5 | `load_config` fallback to defaults if file missing/corrupt (AUDIT C2) | own audit | XS | First-run UX, recovery from C1 |
| 0.6 | Add `.gitignore`, `requirements.txt`, `README.md`, `LICENSE` | basic hygiene | S | New contributors / users can find their way |
| 0.7 | Gate `current_video_language` capture on URL match (AUDIT A4) | own audit | XS | Wrong language hint on rapid URL changes |
| 0.8 | Delete partial subtitle file on cancel (AUDIT A5) | own audit | XS | Already a documented limitation |

**Total estimate:** one to two days. The whole of Phase 0 should ship as one PR titled "Phase 0: correctness baseline."

---

## Phase 1 — Foundation (next 2-3 weeks)

Set the stage for sustainable growth: modern look, sane logging, proper packaging, tests. None of this is user-visible feature work, but every later phase depends on it.

### 1.1 Modern theme with sv-ttk — DONE (Phase 1a)

- **Source:** rdbende/Sun-Valley-ttk-theme
- **Effort:** XS (10 minutes)
- **Why:** Default Tk look is the single biggest "amateur software" signal. Two lines of code give us Windows 11 styling for free.
- **Implementation:**
  ```python
  import sv_ttk
  sv_ttk.set_theme(self.app_config.get("theme", "dark"))
  ```
  Add a theme picker (Light / Dark / System) in a new Settings dialog.

### 1.2 platformdirs for config and logs — DONE (Phase 1a)

- **Source:** standard practice
- **Effort:** S (2 hours)
- **Why:** Today `config.json` lives next to the executable. That breaks the moment we ship a signed installer that puts the exe in `Program Files\` (read-only). It also forces every user on a shared machine to share settings.
- **Implementation:**
  - `config.json` → `%LOCALAPPDATA%\WhisperProject\config.json` (via `platformdirs.user_config_dir`)
  - First-run migration: if old `config.json` is next to the exe, copy it to the new location and rename old to `.bak`
  - Model cache → `%LOCALAPPDATA%\WhisperProject\models\` instead of the current `X:\whisper_cache2\...`

### 1.3 Proper logging — DONE (Phase 1a)

- **Source:** standard practice
- **Effort:** S
- **Why:** Currently a mix of `print()` and a Tk Text widget. Crash diagnostics are lost when the user closes the app.
- **Implementation:**
  - `logging.getLogger(__name__)` in every module
  - `RotatingFileHandler` at `%LOCALAPPDATA%\WhisperProject\logs\app.log`, 5 MB × 3 backups
  - Worker subprocess uses a `QueueHandler` that writes to stderr (parent already captures stderr)
  - Stdout protocol stays JSON-only — see AUDIT B7
  - "Open log folder" menu item

### 1.4 Split `gui.py` (Phase 1 of refactor)

- **Source:** common Python desktop project structure
- **Effort:** M
- **Why:** 1156 lines blocks understanding and testing. See AUDIT B1.
- **Implementation:** the conservative split first — keep `App` class, but extract:
  - `app/dialogs/model_dialog.py` ← `ModelDownloadDialog`
  - `app/domain/tasks.py` ← `TranscriptionTask`, `VideoDownloadTask`
  - `app/domain/languages.py` ← `SUBTITLE_LANGUAGES`
  - `app/services/format_service.py` ← `lookup_formats`, `poll_format_events`
  - `app/services/download_service.py` ← `build_download_command`, `build_subtitle_command`, `process_download_queue`, `poll_download_events`
  - Whatever's left in `gui.py` is the `App` class wiring the rest together. Should be under 400 lines.

### 1.5 `requirements.txt` / `pyproject.toml` — PARTIALLY DONE (Phase 1a)

- **Source:** standard
- **Effort:** XS
- **Why:** AUDIT D18.
- **Implementation:** `pyproject.toml` with `[project.optional-dependencies]` for `gpu`, `dev`, `test`. Pin lower bounds, not upper.
- **Status:** `requirements.txt` ships sv-ttk and platformdirs in active deps. `pyproject.toml` migration deferred to Phase 1b.

### 1.6 Tests for `core/` (Phase 1 of test coverage)

- **Source:** standard
- **Effort:** M
- **Target coverage:** 80% on `core/`
- **Priority order:**
  1. `tests/test_subtitle_lang_args.py` — pure-function, written first as a smoke test of the test infra
  2. `tests/test_model_manager.py` — mock `requests`, exercise MD5 parsing, mismatch handling, resume from partial download
  3. `tests/test_worker_protocol.py` — spawn worker, feed a 1-second silent WAV, assert event sequence
  4. `tests/test_config.py` — atomic write, fallback to defaults
- Add GitHub Actions CI: pytest + ruff + (optionally) pyright

### 1.7 Type hints on `core/`

- **Source:** standard
- **Effort:** S
- **Why:** AUDIT B2.
- **Implementation:** strict pyright on `core/`, basic on `app/`. `pyproject.toml`:
  ```toml
  [tool.pyright]
  include = ["core", "app"]
  strict = ["core"]
  ```

### 1.8 Sentry crash reporting

- **Source:** common practice
- **Effort:** XS
- **Why:** Free tier is generous, and we have zero visibility into user-side failures today. Especially important for the model download path which has many failure modes.
- **Implementation:** `sentry_sdk.init(dsn=..., traces_sample_rate=0.0, before_send=scrub_pii)`. A setting to disable it. Privacy disclosure in README.

---

## Phase 2 — Whisper as a serious transcription tool (next 1-2 months)

These features take us from "wraps faster-whisper with defaults" to "comparable to Buzz / CheshireCC / WhisperX for the workflows we care about."

### 2.1 Voice Activity Detection (VAD)

- **Source:** Whisper-WebUI, Buzz, Purfview/whisper-standalone-win
- **Effort:** XS (one line) + S (UI)
- **Why:** Single biggest accuracy win. Eliminates hallucinations on silence and music. Should be on by default.
- **Implementation:**
  ```python
  segments, info = MODEL.transcribe(
      file,
      vad_filter=True,
      vad_parameters=dict(
          min_silence_duration_ms=settings.vad_min_silence_ms,
          speech_pad_ms=settings.vad_pad_ms,
          threshold=settings.vad_threshold,
      ),
  )
  ```
  UI: checkbox (default on) + advanced panel with two sliders.

### 2.2 Word-level timestamps

- **Source:** every modern Whisper GUI
- **Effort:** S
- **Why:** Karaoke-style subtitles, accurate line splits at word boundaries, color-coded low-confidence words, foundation for the integrated editor (2.7).
- **Implementation:** `word_timestamps=True` adds a `words: list[dict]` per segment. Include in the JSON output. Use for VTT karaoke and LRC formats.

### 2.3 Language detection display

- **Source:** Buzz, CheshireCC
- **Effort:** XS
- **Why:** `info.language` and `info.language_probability` are already returned. We just don't show them.
- **Implementation:** emit a `language_detected` event from the worker; show "Detected: Persian (97%)" in the UI before transcription kicks in.

### 2.4 Multi-format output

- **Source:** standard across all competitors
- **Effort:** S
- **Why:** AUDIT D12.
- **Implementation:** factor the output writers out of `transcriber.transcribe()` into a `core/writers/` module: `SrtWriter`, `VttWriter`, `TsvWriter`, `JsonWriter`, `TxtWriter`, `LrcWriter`. Steal logic from `openai-whisper`'s `whisper/utils.py` (MIT-licensed, well-tested).

### 2.5 BatchedInferencePipeline for GPU

- **Source:** faster-whisper documentation
- **Effort:** XS
- **Why:** 3-12× speedup on GPU for long files. One-line wrapper.
- **Implementation:**
  ```python
  if device == "cuda":
      MODEL = BatchedInferencePipeline(model=MODEL)
  ```

### 2.6 Robust device detection with CTranslate2

- **Source:** AUDIT D14, faster-whisper best practice
- **Effort:** S
- **Why:** Current `torch.cuda.is_available()` check requires torch even on CPU users. CTranslate2 has native device introspection.
- **Implementation:** replace `detect_device` with `ctranslate2.contains_cuda_device()` and `ctranslate2.get_supported_compute_types()`. Drop the torch dependency entirely (we don't need it for inference).

### 2.7 Model picker + lazy model downloader

- **Source:** CheshireCC, cbro33
- **Effort:** M
- **Why:** Today the user gets exactly one model (`large-v3`, 3 GB on disk). Need at least:
  - `tiny`, `base`, `small`, `medium`, `large-v3` — official whisper sizes
  - `distil-large-v3` — 6× faster, English-only
  - Custom HuggingFace repo ID (`Systran/faster-whisper-...`)
- **Implementation:** rework `config.json` to `{ "models": [...], "active_model": "large-v3" }`. UI: a model picker in Settings; the model is downloaded on first use, not at startup. Reuse the existing `ensure_model` + MD5 verify path with per-model URL/manifest.

### 2.8 Initial prompt and hotwords UI

- **Source:** faster-whisper docs
- **Effort:** S
- **Why:** Domain accuracy on names like "Supreme Master Ching Hai", "Loving Hut", proper nouns and jargon improves dramatically. Cheap to expose.
- **Implementation:** a multi-line text field for `initial_prompt` and a single-line field for `hotwords`. Saved per-preset (2.10).

### 2.9 Translate-to-English toggle

- **Source:** Whisper-WebUI, CheshireCC
- **Effort:** XS
- **Why:** AUDIT D9. The user produces bilingual content; toggling `task="translate"` produces English from Persian audio.
- **Implementation:** radio buttons "Transcribe / Translate to English."

### 2.10 Preset system

- **Source:** dsymbol/yt-dlp-gui, Stacher
- **Effort:** M
- **Why:** Save a named bundle of settings (model, VAD params, initial_prompt, hotwords, output formats, output folder template) and apply with one click. Critical for the BMD workflow.
- **Implementation:** `~/.config/whisper-project/presets/<name>.toml`. Preset picker in the main UI. Ship 3-4 starter presets: "Supreme Master TV (Persian)", "Podcast English", "Music video", "Meeting notes".

### 2.11 Subtitle splitting heuristics

- **Source:** stable-ts, Netflix/BBC subtitle standards
- **Effort:** M
- **Why:** Raw segments from faster-whisper are often too long for TV display. Industry standards: max 42 chars/line, max 2 lines, CPS ≤ 17, min display 0.83s.
- **Implementation:** post-processor in `core/writers/` that consumes word-level timestamps and emits clean subtitle blocks. Configurable.

### 2.12 Drag-and-drop + folder watcher

- **Source:** CheshireCC, Buzz
- **Effort:** S (DnD) + M (folder watcher)
- **Why:** AUDIT D6, D7.
- **Implementation:**
  - DnD: `tkinterdnd2` on the Transcribe tab
  - Folder watcher: a separate tab "Watch folder", uses `watchdog` to enqueue new files automatically. New audio/video files appearing in the watched folder get transcribed.

---

## Phase 3 — yt-dlp as a serious downloader (1-2 months)

Currently the yt-dlp tab is a working download front-end. To compete with yt-dlg, Tartube, Open Video Downloader, etc., we need feature parity on the things that matter most.

### 3.1 `--progress-template "%(progress)j"` for robust progress

- **Source:** best-practice across modern yt-dlp wrappers
- **Effort:** XS
- **Why:** Today we regex `[download] N.N%` from stdout. Fragile (the format can change). `--progress-template "%(progress)j"` emits one JSON line per progress event with `downloaded_bytes`, `total_bytes`, `speed`, `eta`.
- **Implementation:** add the flag, replace `percent_re` parsing with `json.loads(line)`.

### 3.2 Auto-update yt-dlp.exe, but properly (fixes AUDIT A1)

- **Source:** cbro33, Seal
- **Effort:** S
- **Why:** AUDIT A1 — the current implementation breaks downloads if the update fails. Need a non-blocking, opt-in update with rate-limiting and SHA256 verification.
- **Implementation:**
  - On launch, async check `https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest`
  - Compare with `bin/yt-dlp.exe --version`
  - If newer, prompt the user (or auto-update if they opted in)
  - Verify SHA256 of the downloaded binary
  - Atomic replace
  - At most one check per day, gated by a timestamp in `config.json`
  - **Never run on the user's download click.** Today's `--update` call must go.

### 3.3 Persistent queue and history

- **Source:** yt-dlg, Tartube, Open Video Downloader
- **Effort:** M
- **Why:** AUDIT D10.
- **Implementation:** SQLite at `%LOCALAPPDATA%\WhisperProject\history.db` with two tables:
  ```sql
  CREATE TABLE downloads (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    folder TEXT,
    format_label TEXT,
    status TEXT,    -- queued / running / finished / cancelled / error
    started_at INTEGER,
    finished_at INTEGER,
    output_paths TEXT,  -- JSON array of files written
    error TEXT
  );
  CREATE TABLE transcriptions (
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
  Restore non-finished queue items on app start (mark them "interrupted").

### 3.4 Command preview / editable args

- **Source:** Stacher (their killer feature)
- **Effort:** S
- **Why:** Power users want to add `--cookies-from-browser firefox` or `--throttled-rate 1M` without us building UI for every flag.
- **Implementation:** Ctrl+Enter on the Download tab opens a small dialog showing the full constructed command and an "extra args" text box. Persist the extra args in config.

### 3.5 SponsorBlock integration

- **Source:** Tartube
- **Effort:** XS
- **Why:** AUDIT D16. Single-line addition.
- **Implementation:** checkbox "Skip sponsored segments (SponsorBlock)" → adds `--sponsorblock-remove sponsor,intro,outro,interaction`.

### 3.6 Cookie / auth wizard

- **Source:** Open Video Downloader
- **Effort:** S
- **Why:** Members-only content, age-restricted content, throttling avoidance via account login.
- **Implementation:** in Settings, a section "Authentication" with:
  - "Use cookies from browser" combo (firefox / chrome / edge / brave) → `--cookies-from-browser`
  - Basic auth fields (rarely needed)

### 3.7 Smart queue with concurrency limit

- **Source:** Open Video Downloader, yt-dlg
- **Effort:** S
- **Why:** Today downloads are serial. For users with bandwidth, allowing 2-3 parallel downloads helps.
- **Implementation:** `parallel_downloads` setting (default 1). `process_download_queue` allows up to N concurrent tasks. Use a `threading.Semaphore`.

### 3.8 Throttling and scheduling

- **Source:** Tartube, yt-dlg
- **Effort:** S (throttle) + M (scheduler)
- **Why:** Politeness to source servers, off-peak downloading.
- **Implementation:** `--limit-rate` and `--throttled-rate` flags exposed in Settings. Scheduler: "Start queue at HH:MM" via `after()` or a small APScheduler.

### 3.9 Simple / Advanced mode toggle

- **Source:** YTPTube (Classic Mode in Tartube)
- **Effort:** S
- **Why:** New users find the format combos overwhelming. Simple mode is just URL + Quality dropdown (Best / 720p / 480p / Audio only).
- **Implementation:** a Settings switch; advanced widgets hidden when Simple is on.

### 3.10 Auto-transcribe after download

- **Source:** **no competitor does this** — our unique value proposition
- **Effort:** S
- **Why:** This is the killer integration: download a YouTube video, automatically queue the resulting file for transcription with `language=` set to whatever yt-dlp detected as the original. Today the user has to manually do step 2.
- **Implementation:** a checkbox "Transcribe after download" in the Download tab. On `download_event "done"`, find the saved media file and call `add_transcription_task(file_path, language=task.detected_language)`.

---

## Phase 4 — Editor and viewer (1-2 months)

Take the app from "produces subtitle files" to "produces good subtitle files that the user can edit and refine."

### 4.1 Integrated transcript viewer

- **Source:** Buzz, aTrain
- **Effort:** L
- **Why:** Click a word in the transcript → audio jumps to that timestamp. Re-export after tweaks. This single feature is what justifies the app over a CLI.
- **Implementation:**
  - A new tab "Edit" that opens after transcription completes (or via right-click on a finished item)
  - Left: scrollable transcript view, one row per segment, each cell editable
  - Right: audio player (use `pygame.mixer` or `simpleaudio` or shell out to ffplay)
  - Word-level highlight follows playback position
  - "Save SRT" / "Save VTT" buttons re-emit the file

### 4.2 RTL / Persian text rendering

- **Source:** **own niche** — no competitor handles this well
- **Effort:** M
- **Why:** Persian and Arabic text in Tk widgets renders left-to-right by default, looking broken. The user works heavily with Persian — this is essential for the editor in 4.1.
- **Implementation:** detect RTL languages, switch Text widget to `wrap="word"` with `justify="right"`, set font to a Persian-supporting one (Vazirmatn, Sahel, or system default). Ship Vazirmatn TTF in `bin/fonts/` and load via `tkextrafont` if needed.

### 4.3 Bilingual side-by-side editor

- **Source:** **own niche** — built for the Supreme Master TV / BMD workflow this user lives in
- **Effort:** L
- **Why:** Many of the user's transcripts end up as bilingual EN | FA subtitle files. Having a column view where each row pairs English and Persian and the user can edit either side is faster than two passes in SubtitleEdit.
- **Implementation:** extension of 4.1. The Persian side starts as machine-translated (via `task="translate"` for Persian→English, but the user often wants the reverse — we'd integrate a small NLLB-200 model or hook an external translator). Aligns to English timestamps.

### 4.4 Subtitle quality linter

- **Source:** subtitle-edit, professional workflows
- **Effort:** M
- **Why:** Flag rows that violate Netflix/BBC rules: CPS > 17, line length > 42, gap < 0.083s, etc.
- **Implementation:** column in the editor that shows a colored badge per row; tooltip with the specific violation.

### 4.5 Word-confidence visualization

- **Source:** Buzz, Pikurrot/whisper-gui
- **Effort:** S (depends on 2.2)
- **Why:** Help the user find places to review. Words with `probability < 0.5` get underlined red.
- **Implementation:** color tags in the Text widget tied to word confidence from 2.2.

---

## Phase 5 — Power features (when there's appetite)

These are the items that take the project beyond "best-in-class for our niche" into "ambitious."

### 5.1 Speaker diarization (pyannote.audio / WhisperX)

- **Source:** WhisperX, Whisper-WebUI, Buzz
- **Effort:** L
- **Why:** AUDIT D11. Meeting / podcast / interview use cases.
- **Implementation:** add WhisperX as an optional dep. Checkbox "Identify speakers." Output adds `SPEAKER_00`, `SPEAKER_01` to SRT.

### 5.2 Vocal separation (Demucs / UVR)

- **Source:** CheshireCC (Demucs), Whisper-WebUI (UVR)
- **Effort:** L
- **Why:** Massively improves transcription quality on music videos and clips with heavy background music. Especially useful for the user's Supreme Master TV workflow where some content is musical.
- **Implementation:** `demucs` is pip-installable but adds heavy deps. Opt-in. Pre-process the audio file before passing to Whisper.

### 5.3 Live microphone transcription

- **Source:** Buzz, Const-me/Whisper
- **Effort:** L
- **Why:** Meeting notes use case. Probably out of scope but worth noting.
- **Implementation:** `sounddevice` + a rolling 5-second buffer + faster-whisper streaming on `tiny.en` or `distil-large-v3`.

### 5.4 REST API server mode

- **Source:** Whisper-WebUI, speaches
- **Effort:** L
- **Why:** Run on a GPU box, control from a laptop. OpenAI-Whisper-API-compatible endpoint for tool interop.
- **Implementation:** FastAPI app in `app/server/`, launched via `python -m whisper_project serve`. Reuses the same `core/transcriber.py`.

### 5.5 CLI mode

- **Source:** Buzz, Purfview
- **Effort:** S
- **Why:** Automation. `whisper-project transcribe in.mp3 --model large-v3 --vad`.
- **Implementation:** `click` or `argparse` entry point in `app/cli.py`. Wraps the same `core/` services.

### 5.6 Packaging: PyInstaller --onedir + installer

- **Source:** common practice
- **Effort:** M
- **Why:** Users shouldn't need Python installed. `--onedir` over `--onefile` because antivirus false-positives are much rarer.
- **Implementation:**
  - PyInstaller spec file
  - Inno Setup or NSIS for an installer that places files in `Program Files`, registers in Start menu, optional desktop shortcut
  - First-run downloads the model (not bundled in the installer)
  - Code signing — deferred until users complain about SmartScreen

### 5.7 Auto-update for the app itself

- **Source:** Open Video Downloader, cbro33
- **Effort:** M
- **Why:** Users get bug fixes without manual download.
- **Implementation:** version check against GitHub releases on launch. If newer, show a banner. Hand-rolled (not PyUpdater, which is overkill).

### 5.8 Backend abstraction (faster-whisper vs whisper.cpp)

- **Source:** Buzz, sandrohanea/whisper.net
- **Effort:** XL
- **Why:** Apple Silicon and AMD GPU users would benefit from whisper.cpp. CTranslate2 is best-in-class for NVIDIA + CPU.
- **Implementation:** `core/backends/` with `FasterWhisperBackend` and `WhisperCppBackend` implementing a common protocol. Likely defer indefinitely.

---

## Phase 6 — Hardening and operations (ongoing)

Not phase-locked; do as items mature.

### 6.1 Sentry crash reports → fixes

Once 1.8 ships, every release cycle should triage Sentry issues.

### 6.2 Test coverage growth

Phase 1 establishes infra. Goal: 80% on `core/`, 50% on `app/services/`, smoke tests on `app/views/`.

### 6.3 GitHub release workflow

`v1.0.0` tag triggers an Actions workflow that:
- Builds the PyInstaller bundle
- Verifies the SHA256 of bundled binaries
- Uploads the ZIP and an installer to the release
- Updates the latest-version JSON used by 5.7

### 6.4 Internationalization (when 2nd locale arrives)

Start with a simple `dict[str, dict[str, str]]` in `app/i18n.py`. Migrate to Babel only when string count > 100.

### 6.5 Architecture Decision Records

Every chunky choice gets a short ADR in `docs/decisions/NNNN-title.md`. Start now while the rationale is fresh. First three to write:

- `0001-subprocess-workers.md` — why workers, not threads
- `0002-yt-dlp-as-binary.md` — why we ship the exe, not `pip install yt_dlp`
- `0003-md5-zip-model-source.md` — why our own mirror, not HF Hub

---

## What we explicitly are NOT doing

- **Migrating to Electron / web UI.** Cost is enormous, no clear user benefit, breaks the lightweight desktop story.
- **Migrating to PyQt6.** CustomTkinter / sv-ttk / ttkbootstrap give us most of the visual upgrade without the rewrite.
- **Building our own model serving infrastructure.** faster-whisper is sufficient.
- **Cloud transcription.** The app's selling point is offline / private. We're not adding "send to OpenAI" toggles.
- **Mobile.** Different problem domain. The Seal Android app already owns yt-dlp-on-mobile.

---

## Synthesis: the masterpiece thesis

What competitors do well, we adopt (Phases 1–3).

What competitors do poorly, we make our differentiation:

1. **Tight yt-dlp ↔ Whisper integration** (Phase 3.10) — no major Whisper GUI auto-transcribes a downloaded video. We do.
2. **Bilingual Persian-English subtitle workflow** (Phases 2.9, 4.2, 4.3) — no Whisper GUI is RTL-aware or has a side-by-side bilingual editor.
3. **Verified, resumable, mirror-served model downloads** (already shipped, document it) — most projects punt to `huggingface_hub`. We're robust on bad networks.
4. **Subtitle production pipeline** (Phases 2.11, 4.4) — most projects emit raw Whisper output. We emit Netflix-grade subtitles.

If we ship Phases 0, 1, 2, and 3, we are at parity with the leaders. Phases 4 and the differentiation pieces above put us ahead of them in a clearly defined niche.

---

## Appendix: competitor matrix (for reference)

### Whisper GUIs

| Project | UI | Distribution | Stars | Standout feature |
|---|---|---|---|---|
| chidiwilliams/buzz | PyQt6 | PyPI / Flatpak / DMG / MSI | 19.2k | Live mic, folder watcher, integrated editor |
| jhj0517/Whisper-WebUI | Gradio (web) | Docker | 2.8k | UVR vocal separation, NLLB translation, diarization |
| CheshireCC/faster-whisper-GUI | PySide6+Fluent | exe | 2.9k | WhisperX, Demucs, karaoke output |
| Purfview/whisper-standalone-win | CLI | standalone exe | 3.0k | 7 VAD methods, --batch_recursive |
| BANDAS-Center/aTrain | Flask+webview | MS Store / Flathub | 1.1k | GDPR-conscious, MAXQDA/ATLAS.ti export |
| Const-me/Whisper | C#/WinForms | portable ZIP | 10.4k | DirectCompute GPU (any vendor) |
| Pikurrot/whisper-gui | Gradio | install wizard | 429 | WhisperX, word+sentence timestamps |
| m-bain/whisperX | (lib only) | pip | 21.8k | Forced alignment, diarization pipeline |
| cbro33/Faster-Whisper-XXL-GUI | Tkinter | exe | 85 | Closest-shape competitor — yt-dlp integrated! |

### yt-dlp GUIs

| Project | UI | Distribution | Stars | Standout feature |
|---|---|---|---|---|
| oleksis/youtube-dl-gui (yt-dlg) | wxPython | MSIX / winget / Snap | ~2k | History, scheduling, throttling |
| jely2002/youtube-dl-gui (OVD) | Vue 3 + Tauri | exe / dmg / AppImage | 8.2k | Smart queue, cookies, notifications |
| StefanLobbenmeier/youtube-dl-gui | Electron | Win/Mac/Linux installers | 2.6k | 32 concurrent downloads, size estimates |
| axcore/tartube | GTK 3 | exe / deb | 3k+ | DB hierarchy, livestream, SponsorBlock |
| dsymbol/yt-dlp-gui | PySide6 | portable ZIP | 1.4k | TOML presets |
| Stacher | Electron | commercial | — | Editable command preview |
| JunkFood02/Seal | Kotlin Compose | APK / F-Droid | 23.6k (Android) | aria2c multithread, Material You |
| arabcoders/ytptube | Python+Vue (web) | Docker | — | Conditions/per-link options, scheduled feeds |
