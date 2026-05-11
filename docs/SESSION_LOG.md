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
