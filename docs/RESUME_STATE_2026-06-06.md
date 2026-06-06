# RESUME STATE — 2026-06-06 (READ FIRST after any context compaction)

Dense, factual snapshot so work continues without re-discovery. Authoritative
details also in `docs/SESSION_HANDOFF_NEXT.md` + `docs/CHANGELOG.md [Unreleased]`.

## Mainline / gate
- Branch: **master**. ~78 local commits since baseline `53fc8b2`. **NOTHING PUSHED.**
  No version bump (still 1.3.7). Do NOT push / tag / release until the owner says so.
- Gate: `pyright app core` must be **0/0/0** (verified repeatedly green). The harness
  "new-diagnostics" pop-ups are frequently STALE mid-edit snapshots (they referenced
  removed worktrees + `log_threadsafe`/`updates` symbols that DO exist) — **trust a
  fresh `pyright app core` run as ground truth, not the inline diagnostics.**
- Hermetic tests: `python -m pytest tests/ --ignore=tests/smoke -q`. KNOWN
  pre-existing (NOT our regressions): `test_resume_from_cancellation.py` (2 tests,
  order-dependent — fail in isolation even at the baseline commit),
  `test_v08_real_file_e2e.py` (needs the real 3 GB model), and a Python-3.14 Tk flake
  ("Can't find a usable tk.tcl") that hits a DIFFERENT Tk-root test each full run but
  passes in isolation. Use `-p no:randomly` + `--deselect` the resume tests +
  `--ignore` test_v08 for a clean signal.

## DONE this session (Phases 1–3, all on master, local-only)
- **Phase 1 (9):** R5 model-hub → %LOCALAPPDATA%\WhisperProject\Cache\models (fixes
  "access is denied"; HUB_SUBFOLDER_NAME="models" so an existing model is reused, not
  re-downloaded); R4 UNC drag-drop; R3 GPU/CPU self-heal + device badge + CPU warning;
  R2 per-task pause/cancel action bars (+ download stop-and-continue pause); R8 tiling
  multi-monitor rewrite (core/tiling.py + core/monitors.py); R1 stdlib LAN/web `gui.py
  serve`; R6 Gemini cloud STT (`cloud_stt`); R9 GitHub update check; R7 Gemma-4 SKIP doc.
- **Phase 2:** real Google Cloud STT backend, one-click Web/LAN toggle tab, batch mode,
  usage display, enriched About.
- **Phase 3 (bug fixes):** `_ServerTask` paused crash (was `_CancelledTask`); View-
  transcript native VLC crash (deferred HWND bind); re-detect-hardware UI freeze (off-
  thread + timeout-bounded cuDNN/cuBLAS probe); queue action-bar selection wiped by the
  500ms refresh; off-thread Tk writes in tiling log + 4 Advanced handlers (new
  `App.log_threadsafe`); + smaller ones (status-cell after_idle, start_tiling guard,
  pause_download guard, guarded save_config, DEFAULT_CONFIG minimise_to_tray/
  telemetry_opt_in, multi-file bulk enqueue, mousewheel unbind, server handle reg order).
- **Phase 3 (features):** VLC seek/scrub transport bar; Web feature parity (per-job
  `.whisperproject.json` overrides, GET /api/jobs, pause/resume, outputs from
  task.output_paths, 3-view browser UI, streaming uploads, HTTP hardening); **SMTV
  transcription docx** format (key `smtv_docx`, bundled template
  `core/writers/templates/smtv_template.docx`, 4-col table, HH:MM:SS.m); installer
  Video-Tiling opt-out (`{app}\no_tiling.flag` → `core.hub.tiling_tab_enabled()`).

## Google Cloud STT — LIVE-VERIFIED ✅ (key facts)
- Service-account JSON: `C:\Users\Owner\Desktop\whisper_project_claude\crucial-context-297802-71bbe43c6f33.json` (project crucial-context-297802, whisper-stt@…). Valid.
- The **user config** (`%LOCALAPPDATA%\WhisperProject\config.json`) was set to:
  `transcribe_backend=google_cloud_stt`, `gcloud_stt_credentials_json=<that path>`,
  `gcloud_stt_model=chirp_2`, `gcloud_stt_location=us-central1`, `hub_folder=…\Cache\models`.
  → the app DEFAULTS to cloud now (uploads audio). Switch back via Advanced → Backend → faster_whisper.
- Empirical (real Google calls): `long`/`global` rejects `"auto"`; `chirp_2` exists only
  in a REGION (us-central1), supports BOTH `"auto"` and BCP-47; bare ISO ("en","fa") is
  REJECTED — need BCP-47 (en-US) or "auto". With `enable_word_time_offsets=True`,
  chirp_2 gives good per-word timing → a 2-min clip produced 5 correctly-timed segments.
  Backend already fixed for all this (chirp_2/us-central1 default + ISO→BCP-47 map + always word offsets + phrase grouping).
- `google-cloud-speech` is installed in the DEV Python 3.14 env (for live tests). In the
  app it installs on-demand via `core.optional_deps` ("google_cloud_stt" feature). Batch
  mode additionally needs a GCS bucket + the SA having Storage Object Admin.

## Build artifacts (rebuilt 2026-06-06 with all phase-3 code; for the owner + a friend)
- `dist_installer\WhisperProject-v1.3.7-Setup-Standard.exe` (~209 MB)
- `dist_installer\WhisperProject-v1.3.7-Portable.zip` (~326 MB)
- Build cmds: `build_embed_installer.bat` → `embed_build\` ; ISCC.exe `installer_embed.iss`
  → the Setup-Standard.exe ; `python -c "import shutil; shutil.make_archive(...Portable, 'zip', embed_build)"`.
  ISCC at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`. Build takes ~15 min + ~5 min installer.
- Visual test PASSED: built app launches, all 5 tabs render (Transcribe / Transcription
  Queue / Download Videos / Video Tiling / Web/LAN access), no crash. Screenshot method:
  Start-Process embed pythonw gui.py → GetWindowRect (user32 P/Invoke) → CopyFromScreen.
- Persian reports on the Desktop: `گزارش نهایی پروژه ویسپر ۲۰۲۶-۰۶-۰۶.docx`,
  `گزارش پروژه ویسپر ۲۰۲۶-۰۶-۰۶.docx`, `گزارش ویسپر فاز ۳ — ۲۰۲۶-۰۶-۰۶.docx`.

## NEW-JOBS source files (P4 inputs) — `C:\Users\Owner\Desktop\new jobs\`
- `claude_request_v1.38.txt` — the P4 spec text (3-level config, multi-model, format
  conversion, usage stats, ffplay link, + the SMTV docx spec which is DONE).
- `work title -Transcription in ... – Translation in English.docx` — the SMTV template (already bundled into the repo + writer DONE).
- `translation-stats-updated-sample.php` — reference for the P4-4 PHP stats tracker.

## P4 BACKLOG — NOT YET STARTED (tasks #29–#33 in the persistent task list)
- **P4-1** three-level merged config: hard-coded DEFAULT_CONFIG ← online JSON (from a
  URL, e.g. GitHub) ← local file; priority local > online > hard-coded. App-level keys
  (model URLs, usage/stats URL, latest version, ffplay links) come from the ONLINE config
  so they change without redistributing. Merge in core/config.py, fail-safe offline.
- **P4-2** config-driven multi-model + Advanced model selector: large-v3 default; add
  faster-whisper-medium, whisper-large-v3-turbo, faster-distil-whisper-large-v3.5
  (find their URLs/MD5). MODEL_REGISTRY + `whisper_model` already exist → make it config-driven.
- **P4-3** transcription format conversion: JSON↔SRT/VTT/TSV/TXT (faster-whisper JSON as
  the middle format) + import .otr (core/integrations/otranscribe.py exists). UI action.
- **P4-4** usage stats: add an integer word-count column to the sqlite `transcription`
  table (core/history.py); a PHP web service (IP/geoip via https://smch.ir/stats/geoip/
  index.php?ip={ip} → country_name, full geoip JSON, filename, model, language, duration,
  AI time, status); the app POSTs stats (respect telemetry opt-in). PHP is a deliverable file.
- **P4-5** ffplay download links (Windows/macOS) in the (online/merged) config → auto-fetch
  ffplay for Video Tiling instead of the "drop ffplay in bin" message.

## Orchestration notes (how I worked; avoids re-learning)
- Heavy use of subagents (Agent tool, inherit Opus 4.8) keeps the main context lean.
- Single git index → no two committing agents at once. For parallelism, used
  `isolation: "worktree"` agents (disjoint files), then `git cherry-pick <hash>` their
  commits onto master (their worktree branches were stale-based on origin/master; they
  reset to the current tip first, which made cherry-pick clean). Verify pyright after each merge.
- English-only repo; commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Owner context
- Owner is non-technical, Persian; full autonomy granted (proceed to completion, local-only,
  real tests + debug allowed). Wants ZERO bugs. Keeps adding request batches; "continue to
  the end of all items" + "test/debug the frontend maximally."

## UPDATE — P4 ALL DONE (commits ~4e71068 … b3801b0; pyright app core 0/0/0)
- P4-1 three-level merged config (local > online URL > hard-coded) + cache/fail-safe; new keys config_url / model_catalog / stats_url / latest_version / ffplay_downloads.
- P4-2 config-driven model catalog + Advanced model selector (large-v3 default; medium/turbo/distil entries; medium URL on smch.ir flagged for the owner to upload).
- P4-3 core/convert.py (parse SRT/VTT/TSV/JSON + .otr → segments → emit any text format) + File→"Convert transcript…" menu.
- P4-4 core/history.py word_count column (idempotent) + core/stats.py opt-in POST (gated on telemetry_opt_in) + stats/transcription_stats.php (deploy to host).
- P4-5 core/tiling.py download_ffplay + "Download ffplay" button; ffplay_downloads default URLs (BtbN win zip / evermeet mac) — OWNER MUST VERIFY/host real URLs via the online config.
- OWNER ACTIONS: host the online config JSON at config_url; set the real stats_url + deploy the PHP; upload faster-whisper-medium to smch.ir; verify ffplay URLs.

## UPDATE — P5 + P6 DONE, ARTIFACTS REBUILT (2026-06-06 19:30; pyright app core 0/0/0; 102 local commits)
- **P5 (frontend bug-hunt):** all surfaced bugs fixed — incl. the deferred LOW ffplay
  guard (`core/tiling.py download_ffplay` now rejects a 0-byte/truncated extract:
  size must be > 100 KB, else the stub is unlinked so a retry re-downloads) + the
  gcloud-stt / stats / smtv-docx / config-merge fixes (commits 03a2375 … f9cd426).
- **P6 (macOS):** PyInstaller `.app` spec (`platform/macos/pyinstaller/whisper_project_mac.spec`,
  tracked via gitignore negation, synced with onedir); tiling spawns players with
  `start_new_session` so Stop's `killpg` never kills the whole app on macOS; macOS
  docs + ffplay-into-bin note; cross-platform test coverage.
- **Version: still 1.3.7 — NOT bumped** (owner 2026-06-06: "keep 1.3.7"). 4 version
  locations all read 1.3.7 (`pyproject.toml`, `core/__init__.py`, `installer_embed.iss`,
  `installer.iss`).
- **Artifacts rebuilt with ALL fixes (Phases 1–6):** `dist_installer\WhisperProject-v1.3.7-Setup-Standard.exe`
  (219,504,174 B) + `WhisperProject-v1.3.7-Portable.zip` (326,446,926 B), both 19:29–19:30.
  Method = incremental: re-copy HEAD `app/`+`core/`+`gui.py` over the intact tested
  `embed_build\` runtime → sanity import (full stack + all new core modules + tiling) →
  ISCC `installer_embed.iss` → `shutil.make_archive` Portable. Launch-smoke PASSED
  (window "Whisper Project v1.3.7", no startup crash). Rebuild helper (gitignored):
  `.claude\rebuild_137.ps1`.

## (historical) earlier note, now SUPERSEDED by the rebuild above
- ⚠ REBUILD NEEDED to ship P4: the dist_installer\*.exe / *.zip are PHASE-3 only. To rebuild: `build_embed_installer.bat` → `ISCC.exe installer_embed.iss` → `python -c "import shutil; shutil.make_archive(...Portable,'zip','embed_build')"` → relaunch embed pythonw gui.py for a visual smoke. (A rebuild may have been kicked off in the background near the end of the session — check dist_installer timestamps.)
