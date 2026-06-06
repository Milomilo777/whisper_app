# Next session — read THIS FIRST

Single-source-of-truth handoff for the next development session on
this repo. Read this file before anything else.

---

## 0. Latest session — Phase 1 (9 changes) + Phase 2 (cloud + web/LAN) + Phase 3 (bug fixes + features) (2026-06-06) — LOCAL ONLY

**Current state: the v1.3.7 baseline + the Phase-1 nine changes + the
Phase-2 additions + the Phase-3 bug-fixes/features, all committed on
`master`, NOT pushed and NOT released.** No version bump, no tag — the
owner will authorise the push + release later. pyright `app/ core/` is
0/0/0 and the targeted suites stay green. Full bullets are in
`docs/CHANGELOG.md` `[Unreleased]` (and worded user-facing there).

> **Reiterate (do not skip):** everything in §0 (Phases 1–3) is **local
> only** — committed on `master`, **not pushed**, **no version bump / tag**.
> A release would still need the version bump in the **4 usual places**
> (`core/__init__.py` `__version__`, `pyproject.toml`, `installer.iss`,
> `installer_embed.iss` `#define MyAppVersion`) — see §3 — and is only cut
> when the owner authorises it.

The Phase-1 9 changes (grouped):

- **Model hub default → `%LOCALAPPDATA%\WhisperProject\Cache\models`**
  (was the install dir → "access is denied" for non-admin users). Added a
  typed `ModelDestinationNotWritable` + a re-pick flow in the
  model-download dialog, a writability probe in the hub picker, and aligned
  the default hub with `model_folder_for`'s empty-hub fallback
  (`HUB_SUBFOLDER_NAME = "models"`) so an existing `Cache\models` model is
  **reused, not re-downloaded** (~3 GB). Verified with a real
  `load_config()` probe on this machine.
- **GPU/CPU autodetect hardening** — a cheap cuDNN/cuBLAS runtime-load gate
  (CUDA only when usable); a self-healing model load that falls back to CPU
  int8 instead of crashing the worker (or falsely prompting a ~3 GB
  re-download); the effective device reported additively on the worker
  `ready` event; a live GPU/CPU badge + a one-time "running on CPU (slower)"
  warning gated to the GPU-detected-but-unusable case (`cpu_warning_shown`).
- **Always-visible per-task action bars** under both Queue tabs
  (Pause / Resume / Cancel / Re-run / Remove) + a status-cell click toggle;
  right-click menu + Esc kept. Download "pause" is stop-and-continue (keeps
  the `.part`, resumes via yt-dlp `-c`/`--continue`); disabled for SMTV
  downloads (no resume point).
- **Network / UNC drag-and-drop fix** — a backslash-preserving, brace-aware
  splitter so a `\\server\share\file` drop is no longer silently dropped
  (`tk.splitlist` was collapsing the leading `\\`).
- **Optional LAN/web server** — `python gui.py serve [--port] [--host]
  [--lan] [--token] [--max-upload-mb]`. Loopback by default (no firewall
  prompt); `--lan` is the explicit opt-in. Browser page + JSON API
  (upload OR URL jobs, progress poll, result download); in-process
  sequential transcription keeps the model hot; bounded queue + upload cap
  + optional token; jobs recorded to history. New Tk-free `core/server/`
  package; new keys `server_port` / `server_max_upload_mb`. Verified live
  here (`/api/health`, `/api/formats`, `/` all 200).
- **Multi-monitor Video Tiling rewrite** — a Tk-free engine (ported from
  the maintainer's `video-tiler` v1.1): one download fanned out to one
  `ffplay` per selected monitor, `poll()` liveness, exponential-backoff
  reconnect, self-heal `yt-dlp -U`, robust extraction, http(s) validation,
  clean teardown via `core._proc.kill_process_tree`. New `core/monitors.py`
  (screeninfo → ctypes Win32 → single-monitor fallback). New keys
  `tiling_quality` / `tiling_mute` / `tiling_multi_monitor` /
  `tiling_selected_monitors` / `tiling_auto_restart`. New optional dep:
  **screeninfo**.
- **Optional Google Gemini cloud STT backend** (`cloud_stt`) — paste a free
  AI Studio API key, transcribe via the Gemini API over stdlib REST
  (default `gemini-3.5-flash`, configurable), chunked upload via the Files
  API. Honest *local* minutes counter + a billing-console link. Loud
  privacy opt-in (uploads audio to Google → breaks the offline guarantee).
  New keys `cloud_stt_api_key` / `_model` / `_minutes_used` /
  `_free_minutes_cap` / `_chunk_seconds`.
- **Opt-in GitHub update check** (notify-only, never auto-installs) in
  `core/updates.py` + a Help-menu "Check for updates" + a throttled quiet
  launch check; silent on private-repo/offline/up-to-date. Documented that
  the Standard installer already upgrades **in place** (stable Inno
  `AppId`). New keys `update_check_enabled` / `last_update_check`.
- **Docs-only** — `docs/evaluations/GEMMA4_EVALUATION_2026-06.md`:
  recommends SKIP of Gemma 4 12B for transcription (30 s cap,
  torch/BF16/~24 GB VRAM, no word timestamps, no WER win), with a
  future-adjunct path + hardware-gate sketch.

### Phase 2 — real Google Cloud STT + one-click Web/LAN (same 2026-06-06 batch)

Committed locally on top of the Phase-1 nine (see the `git log` tail:
`9fd5b3b` … `a2d05f9`). Still LOCAL ONLY, still 1.3.7-labelled.

- **Real Google Cloud Speech-to-Text backend** (`google_cloud_stt`, new
  `core/backends/google_cloud_stt.py`) — a second, more capable cloud
  option next to the simple Gemini one. Authenticates with a
  **service-account JSON file** (NOT a pasted key) via the official
  `google-cloud-speech` **v2** client, installed **on demand on first use**
  (`core/optional_deps.py`) — NOT bundled. Two modes: (a) Standard/online —
  decode via ffmpeg, chunk the local file into ≤ ~55 s pieces, `recognize()`
  inline per chunk, offset + stitch timestamps, no Cloud Storage (~$0.016/min);
  (b) Batch — v2 `BatchRecognize` via a user-supplied GCS bucket (`gs://`),
  `DYNAMIC_BATCHING`, ~$0.004/min (~75 % cheaper) but up to ~24 h turnaround.
  Word-level timestamps + speaker diarization supported. The earlier Gemini
  backend (`cloud_stt`) is KEPT as the simple paste-a-key alternative; both
  labelled in the UI.
- **Cloud STT settings UI** (`app/dialogs/advanced.py`) — backend dropdown
  with human labels for both cloud options; a Google Cloud section with a
  service-account JSON picker, a "How do I get this file?" step-by-step help
  dialog (clickable links to the exact console pages), a non-blocking
  **Test connection** button (installs the libs on demand + validates the
  JSON/auth), a Batch-mode toggle + GCS bucket field, a diarization toggle,
  and a LIVE usage display.
- **Free-tier usage tracking** — a LOCAL **monthly** minutes counter (resets
  each calendar month) + an honest estimated-cost line ("X / 60 free minutes
  this month; estimated $Y of the $300 credit"), labelled a local estimate
  with a billing-console link (the real remaining credit is NOT readable
  from the key). New keys `gcloud_stt_minutes_used` /
  `gcloud_stt_minutes_month` / `gcloud_stt_free_minutes_cap`.
- **One-click Web / LAN access** (`app/app.py` + `app/widgets/tabs.py`, a
  `core/server` `ServerHandle`) — a new **Web / LAN access** tab with a
  single Start/Stop toggle, a port field (free-port fallback when busy), a
  **Share on local network** checkbox (loopback default vs `0.0.0.0` with a
  plain firewall note), an optional access password (token), the reachable
  URL(s) incl. LAN IP, an **Open in browser** button, non-blocking
  start/stop, and auto-stop on exit. New keys `server_share_lan` /
  `server_token` (`server_port` / `server_max_upload_mb` already existed).
- **About dialog enriched** (`app/app.py` `_show_about`) — a "What's new"
  section + plain-language descriptions of all the cloud options, Web/LAN
  access, per-task controls, multi-monitor tiling, and the update check /
  in-place upgrade, with clickable helpful links.
- **New docs** — `docs/CLOUD_STT_GOOGLE.md` (service-account setup + batch +
  honest usage note); `docs/SERVER.md` updated for the one-click toggle. All
  new `gcloud_stt_*` / `server_*` keys documented in `docs/CONFIG.md`.

### Phase 3 — bug fixes + features + live-verified Google Cloud STT (same 2026-06-06 batch)

Committed locally on top of Phase 2. Still LOCAL ONLY, still 1.3.7-labelled,
NOT pushed, NO version bump. From a reported-issues list + a deep
adversarial review. Full user-facing bullets in `docs/CHANGELOG.md`
`[Unreleased]` (`#### Phase 3` blocks under Added / Changed / Fixed / Docs).

Bug fixes:
- **Web / LAN: every job crashed** with `'_CancelledTask' object has no
  attribute 'paused'` — the server task object now mirrors the engine's
  read contract (renamed `_ServerTask`); test fakes hardened.
- **"View transcript" closed the whole app** — libvlc `set_hwnd` on an
  unrealized Tk window (a native crash that bypassed `try`/`except`). Fixed
  by deferring the HWND bind until the window is mapped + a graceful
  fallback; the viewer now opens the actual transcript `.json` (no spurious
  file-picker).
- **"Re-detect hardware" froze the UI** — the probe ran on the Tk main
  thread (+ an unbounded cuDNN/cuBLAS `ctypes.CDLL` probe). Fixed: runs
  off-thread behind a generation-token guard + a timeout-bounded DLL probe.
- **Queue per-task action bar was unusable** — the 500 ms `refresh()`
  rebuilt the tree and wiped the selection; selection is now preserved
  across the rebuild.
- **Off-thread Tk writes fixed** — the Video Tiling log callback + 4
  Advanced-dialog worker handlers now marshal through the main thread (new
  `App.log_threadsafe`); tiling status colour now applied.
- **Smaller** — status-cell click defers via `after_idle`; `start_tiling`
  guards a bad grid spinbox; `pause_download` only pauses a running
  download; theme + download-folder `save_config` guarded;
  `minimise_to_tray` / `telemetry_opt_in` added to `DEFAULT_CONFIG`;
  multi-file enqueue gates the model once; Advanced mouse-wheel binding
  released on close; server handle registered before `start()`.

Features:
- **VLC transcript preview seek/scrub transport bar** — draggable position,
  `MM:SS` readout, ±5 s / ±10 s skip, keyboard; degrades gracefully without
  VLC.
- **Web / LAN feature parity** — per-job advanced options (VAD, word
  timestamps, diarization, clip range, …) via a per-job
  `.whisperproject.json` override; `GET /api/jobs` list; pause / resume
  routes; outputs from the engine's `task.output_paths`; a 3-view browser
  UI (Submit / Jobs / Result with inline transcript); streaming uploads (no
  full-RAM buffering); HTTP hardening (body-drain on early reject,
  constant-time token compare). Cloud / alt backends are NOT per-job
  switchable over the web (security boundary).
- **"SMTV transcription" docx output format** (registry key `smtv_docx`, UI
  label "SMTV transcription") — fills the bundled template
  `core/writers/templates/smtv_template.docx`: a 4-column table (auto row #;
  `Time Code` `HH:MM:SS.m`; `Foreign Language` = transcript; `English
  Translation` empty for the human), title line
  `"<work title> -Transcription in <language> – Translation in English"`,
  filename matched; grows the table past 31 rows; forces a `.docx` extension.
- **Google Cloud STT fixes — LIVE-VERIFIED** with the owner's
  service-account JSON (project `crucial-context-297802`): default
  model/location is now `chirp_2` / `us-central1` (supports auto-detect +
  multilingual; the old `long` / `global` rejected `"auto"`); language codes
  mapped ISO → BCP-47 (Google v2 rejects a bare `"en"`); word time offsets
  always requested + words re-segmented into properly-timed phrases (a real
  run produced 5 correctly-timed subtitle segments instead of one 0–30 s
  blob). `config.py` `gcloud_stt_model` / `gcloud_stt_location` defaults
  updated; `docs/CONFIG.md` + `docs/CLOUD_STT_GOOGLE.md` updated.
- **Installer Video-Tiling opt-out** — a "do NOT include Video Tiling" task
  in `installer_embed.iss` drops a `{app}\no_tiling.flag` marker; the app
  hides the Video Tiling tab when present (`core.hub.tiling_tab_enabled()`).

**SETUP NOTE — the app now DEFAULTS to Google Cloud transcription
(uploads audio to Google):** the owner's service-account JSON at
`C:\Users\Owner\Desktop\whisper_project_claude\crucial-context-297802-71bbe43c6f33.json`
is set as the app default in the user config
(`transcribe_backend = google_cloud_stt` + `gcloud_stt_credentials_json` +
`gcloud_stt_model = chirp_2` / `gcloud_stt_location = us-central1`). This is
the **dev machine's** config, not a shipped default — but be aware the app
here uploads audio to Google by default. **To switch back to offline:**
Advanced > Backend → `faster_whisper`. `google-cloud-speech` installs on
first use (on demand); **batch mode** additionally needs a GCS bucket +
**Storage Object Admin**.

### P4 BACKLOG — planned, NOT yet implemented

New requests from
`C:\Users\Owner\Desktop\new jobs\claude_request_v1.38.txt`. Recorded as
planned for a future session; nothing below is built yet.

- **P4-1 — three-level merged configuration** (hard-coded → online-URL →
  local-file) so model URLs / the usage-stats URL / latest-version /
  ffplay links can change **without redistributing** the app.
- **P4-2 — config-driven multi-model + an Advanced model selector** — add
  `faster-whisper-medium`, `large-v3-turbo`, `distil-large-v3.5`;
  `large-v3` stays the default.
- **P4-3 — transcription format CONVERSION** — JSON ↔ SRT / VTT / TSV / TXT
  (+ `.otr` import), with the faster-whisper JSON as the middle format.
- **P4-4 — usage stats** — a "word count" column in the sqlite
  transcription table + a PHP online stats tracker (IP / geoip via
  `smch.ir`, filename, model, language, duration, AI time, status) + the
  app POSTing stats.
- **P4-5 — ffplay download links in config** for auto-fetch on Windows /
  macOS.

**Build/spec bookkeeping done:** the PyInstaller hidden-import lists in
both `whisper_project_onefile.spec` and `whisper_project_onedir.spec` carry
all the new modules — Phase-1 (`core.server.*`, `core.monitors`,
`core.backends.cloud_stt`, `core.updates`) + **screeninfo** AND the Phase-2
backend (`core.backends.google_cloud_stt`) — both verified present this
session. The `google-cloud-speech` / `google-cloud-storage` libs install on
demand at runtime, so they are deliberately NOT bundled (only the backend
module that imports them lazily is).

**OPEN caveats for the next session (re-check; don't assume done):**
- **R6 Gemini path is UNTESTED end-to-end** — no API key in this
  environment. The owner must live-test with their own key: paste key →
  "Test key" → run one file → confirm a transcript lands and the local
  minutes counter advances.
- **The real Google Cloud STT (`google_cloud_stt`) network path is UNTESTED
  here** — no service-account JSON in the dev environment. The owner must
  live-test: in **Advanced > Backend** pick the JSON file → click **Test
  connection** → run a file. **Standard mode** needs only the JSON + the
  **Cloud Speech-to-Text User** role + the Speech-to-Text API enabled.
  **Batch mode** additionally needs a GCS bucket + **Storage Object Admin**
  on it. The `google-cloud-speech` (+ `google-cloud-storage` for batch) libs
  install on **first use** (on demand), NOT bundled — so the first run with
  this backend will pause to pip-install them.
- **screeninfo is a NEW optional dependency** — multi-monitor tiling
  degrades to single-monitor without it; it's pruned/absent in some build
  trees, so confirm the Monitors chooser behaves when it's missing.

**A build was produced this session** (the build path is appended
separately) — still **v1.3.7-labelled, unreleased, local only**.

**PRE-EXISTING test issues (NOT introduced this session — present at the
baseline commit `53fc8b2`, so not a regression):**
- `tests/core/test_resume_from_cancellation.py` is **order-dependent** —
  it fails in isolation even at baseline `53fc8b2`; passes under the full
  suite ordering.
- `tests/core/test_v08_real_file_e2e.py` is a **real-model E2E** that
  ERRORs under full-suite session ordering (needs the real model + a
  hot worker; not hermetic).
- A Tk-root **"Can't find a usable tk.tcl"** flake on the local Python
  3.14 box (environment quirk, not our code).
- These are why the deferred test-gap items (§0.1 below) still need a
  heavier harness; do NOT treat their flakes as new breakage.

**A release would still need the version bump in the 4 usual places**
(`core/__init__.py` `__version__`, `pyproject.toml`, `installer.iss`,
`installer_embed.iss` `#define MyAppVersion`) before building — see §3.

---

## 0.1. Earlier session — senior-architect deep audit (2026-05-29)

A read-only audit fanned out 8 parallel shards (concurrency, resource
leaks, security, error-handling, data-integrity, cross-platform,
test-gaps, maintainability) → 53 raw findings → 20 verified-real + 32
P2 + 1 rejected. Fixed in 8 themed commit batches, each gated on
`pyright app/ core/` 0/0/0 + the hermetic suite green, pushed to
`master`. Full list in `docs/CHANGELOG.md` `[1.3.7]` (this batch SHIPPED as
v1.3.7 on 2026-05-29). Method + raw findings: `.claude/audit_findings.md`
(workspace, untracked).

**Shipped behaviour:** no change to Windows spawn flags; the fixes are
teardown/robustness/correctness. **Released as v1.3.7** (this was the batch
deferred at the time; it has since shipped).

**Deferred, with reason (re-check; don't assume done):**
- **Test-gaps not yet covered** (cover already-shipped code, lower risk,
  need heavier harnesses): P2-19 headless ready-timeout teardown; P2-21
  crash-resume `_do_resume` closure (needs a Tk-ish fake or a pure-helper
  refactor); P2-22 SMTV `_apply_smtv_formats` mapping (+ a 'max'-quality
  variant is dropped — worth confirming intent); P2-23 Advanced-settings
  `_save_and_close` var→config round-trip (best after extracting a pure
  `collect_advanced_config` helper).
- **P2-31** `ensure_worker_ready(headless=True)` + `start_standby()` are
  dead in production (only tests call them) and would deadlock if reused
  on the Tk thread. Left in place — tests depend on `headless=True` and a
  runtime "am I on the Tk thread?" guard is unreliable. Already documented
  as deprecated in their docstrings; use `_when_worker_ready` instead.
- **REJ-1 (NOT a bug):** the PDF writer not stripping XML-illegal control
  chars was investigated and is harmless — reportlab 4.x uses a lenient
  HTMLParser, not a strict XML parser, so NUL/ESC/etc. build a valid PDF.
  No fix needed (verified empirically).
- **P2-14 (doc-only):** LRC timestamps render 3-digit minutes past 100 min
  (LRC has no hours field); strict players may mis-seek. Left as-is —
  inherent to the format.
- **macOS [13]/P2-16 + Linux**: the ffmpeg-into-bin symlink + non-fatal
  unzip are `bash -n`-clean and reasoned-correct but UNVERIFIED on a real
  Mac. Class-C yt-dlp/ffprobe items (keyframe snap, etc.) untouched —
  still need a real yt-dlp+ffprobe harness before changing.

**Suggested live re-validation next session** (needs the model + test
video): `python tools/e2e_cancel_pause.py` exercises the real worker's
cooperative cancel/pause/resume — confirms the process-tree-kill +
modal-close changes (batches A/C) didn't disturb the cooperative path.

---

## 1. Current state (2026-05-25)

| Item | Value |
|---|---|
| Branch | `master` — **the single mainline**. Published tip is **v1.3.7** (deep-audit hardening, see §0.1). On top of that sit the **2026-06-06 LOCAL-ONLY changes — Phase 1 (9 changes) + Phase 2 (real Google Cloud STT, one-click Web/LAN, enriched About) (see §0) — committed, NOT pushed, NOT released.** Owner will authorise the push/release later. |
| Version | **unchanged — still 1.3.7** in all 4 places (pyproject, `core.__version__`, both `.iss`). This session deliberately did NOT bump — the Phase-1 + Phase-2 changes are unreleased; bump only when the owner authorises the release. |
| Last PUBLISHED release | **v1.3.7** on GitHub (Standard 219 MB + Portable 325 MB) — the deep-audit security/leak/robustness/correctness pass (§0.1); built + slim past-bug E2E PASS + live cancel/pause E2E PASS + hermetic suite green + pyright 0/0/0; published 2026-05-29. |
| GitHub releases now | `v1.3.7` (latest) + `basic-v0.1.0` (separate edition). **POLICY (2026-05-26 owner): keep ONLY the latest release — prune the rest on each release.** v1.3.6 release object was pruned on the v1.3.7 release; its git tag + the local `dist_installer/WhisperProject-v1.3.6-*` artefacts remain as backup. |
| Installed test copy | none built (validated by `tools/e2e_slim_pastbugs.py` + `tools/e2e_cancel_pause.py` against the real worker). The user installs the published EXE themselves. |
| Default GitHub branch | `master` (now the ONLY branch — origin has just `master`) |
| Working tree | local commits ahead of `origin/master` (the §0 nine-change batch + the docs/test-cleanup); untracked tooling (`.claude/`, `PROJECT_INDEX.md`, `AGENTS.md`, `.cursorrules`, `tools/index_refresh.py`) left as-is |
| Gate | `pyright app core` → **0/0/0** (re-verified this session). Full `run_tests.bat` hermetic suite NOT re-run this session — see the PRE-EXISTING test flakes in §0 before reading any red as a regression. |
| Build prereqs (this PC) | Inno Setup `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` ✓ · test video `E:\3029-NWN-Daily-Scroll-2m_0002.mp4` ✓ · extracted model under `%LOCALAPPDATA%\WhisperProject` ✓ |
| Version source of truth | `core/__init__.py` `__version__` (bundled; About dialog + telemetry read it). Bump it with pyproject + both `.iss` every release. |

### What shipped in v1.3.6 (PUBLISHED 2026-05-26)

Video Tiling tab + Linux/macOS groundwork. Full list: `docs/CHANGELOG.md`
+ `docs/RELEASE_NOTES_v1.3.6.md` + the plan in
`docs/CROSS_PLATFORM_ROADMAP.md`. Headlines: **Video Tiling tab**
(`core/tiling.py` + `build_tiling_tab`) — one live stream filled across the
screen as an N×N grid via `yt-dlp | ffplay -vf tile=NxN` (ports
`translation-robot/video-tiler`); **ffplay is NOT bundled** (would bloat
the build), so the tab detects its absence and tells the user to drop
`ffplay.exe` in `bin/` or put ffmpeg on PATH. **Cross-platform core
hardening** — `yt-dlp`/`ffmpeg`/`ffprobe` resolve per-OS via
`core.paths.bundled_binary` (PATH fallback), `--ffmpeg-location` is only
passed when a bundled ffmpeg exists, VLC discovery covers macOS/Linux; the
Windows build is byte-for-byte the same shape. **`platform/linux/`** (one-
step `install.sh` venv + deps + static-ffmpeg fallback + a headless
`whisper-transcribe` CLI + update/uninstall) and **`platform/macos/`**
(`install.command` + `unblock.command` for Gatekeeper + README). A
`.gitattributes` pins LF on `*.sh`/`*.command`.

**Follow-ups for a future session:**
- Video Tiling needs **ffplay** to actually run. To make it work
  out-of-box on Windows, add `bin/ffplay.exe` (from the full ffmpeg build)
  — either commit it (repo already LFS-warns on the ~97 MB ffmpeg.exe) or,
  cleaner, have `build_embed_installer.bat` fetch ffplay into
  `embed_build/bin` at build time. Deferred to keep the build/repo size
  unchanged this release.
- **macOS is unvalidated** — no Mac was available. The code + scripts
  follow best practice but need a real-device run (see `platform/macos/README.md`).
- Linux scripts are `bash -n`-clean but not run on a real distro here; the
  maintainer confirmed transcription works on their Linux server.

### What shipped in v1.3.5 (PUBLISHED 2026-05-25)

Real Pause/Resume/Cancel + a post-slim hardening pass (five parallel
code-audit shards over everything that changed in v1.3.x). Full list:
`docs/CHANGELOG.md` + `docs/RELEASE_NOTES_v1.3.5.md`. Headlines:
**cooperative pause/resume/cancel (#37)** — the worker now reads control
commands on a dedicated `worker-stdin` reader thread and flips the
in-flight task's `cancelled`/`paused` flags while the main thread is busy
in `transcribe()`; the transcriber already polled those between segments
(and flushes a resumable checkpoint on cancel), so only signal delivery
was missing. `app/app.py` pause/resume/cancel now call
`TranscriptionService.send_control(task, action)` instead of killing the
worker; a per-worker `stdin_lock` serialises the three concurrent writers.
**The worker reports the files it actually wrote** in the `done` event
(`task.output_paths` → `finish_task` history + `show_last_result`), so a
docx/pdf-only run no longer shows "no output files found". Plus the audit
fixes: a "transcribing" download row is cancellable; `_fmt_timecode`
sub-second carry (`1:30.999` → `0:01:31`); per-format writer resilience
(one bad writer no longer discards the good ones); pausing a not-yet-
running task is a no-op; `progress_cell`/`marquee_cell` tolerate a
non-finite percent; on-demand installs are serialised + log on the UI
thread; the slim build drops the orphaned `llvmlite.libs` and its sanity
check imports docx/reportlab to guard the docx-regression class. New
tests: `test_worker_control`, `test_cancel_checkpoint` (deterministic
faked-model cancel→checkpoint), done-event outputs, sub-second timecode;
new live driver `tools/e2e_cancel_pause.py`.

### What shipped in v1.3.4 (PUBLISHED 2026-05-25)

Slim install + on-demand optional deps + the docx fix. Full list:
`docs/CHANGELOG.md` + `docs/RELEASE_NOTES_v1.3.4.md`. Headlines:
**slim ~800 MB install** (was ~1.5 GB) — `build_embed_installer.bat`
now prunes the heavy optional libraries (torch, torchaudio,
openai-whisper, stable-ts, numba, llvmlite, sympy, networkx, mpmath)
after pip install; the Standard installer dropped 348 MB → 219 MB and
the Portable ZIP 557 MB → 326 MB. **On-demand optional features**
(`core/optional_deps.py`) — Word-timestamp alignment (stable-ts) and the
openai-whisper backend now `pip install --target` into a user pylibs dir
(~700 MB, one time) the first time they're used; `app/app.py`
`_offer_optional_install` asks first (askyesno + a threaded Toplevel
progress), then restarts the worker. The core stack (faster-whisper) is
still bundled so transcription/subtitles/diarisation/downloads/the
time-range slider all work out of the box. **DOCX (+ PDF) output fix** —
the worker's config snapshot was stale, so `output_formats` never crossed
the process boundary and docx was silently dropped; `output_formats` is
now threaded transcribe_command → worker → `_write_outputs`.
New: `tools/e2e_slim_pastbugs.py` (slim-build past-bug release gate) +
`tests/core/test_optional_deps.py`.

### What shipped in v1.3.3 (PUBLISHED 2026-05-25; pruned then RESTORED — still on GitHub)

Position slider on the Download tab (#39) + clip/range review fixes, and
the first Portable ZIP of the embed tree. Full list: `docs/CHANGELOG.md`
+ `docs/RELEASE_NOTES_v1.3.3.md`. Headlines: a **draggable Start/End
position slider** on the Download tab (`set_download_duration` /
`_on_download_scale`, guarded by `_suppress_scale_cb` + a
`_download_duration<=0` disable) wired to the time-range fields; review
fixes from three code-review shards — the slider `set()` no longer
clobbers typed values, a clipped run forces `resume=False` (no checkpoint
keyed to the whole file), and `start>=end` is dropped to open-ended.

### What shipped in v1.3.2 (PUBLISHED 2026-05-25, now pruned from GitHub)

Security + features, after a second bug-hunt (4 more parallel shards:
concurrency, resource-leaks, hostile-input, security). Full list:
`docs/CHANGELOG.md` + `docs/RELEASE_NOTES_v1.3.2.md`. Headlines:
**SECURITY** — yt-dlp option injection closed (a "-"-prefixed pasted URL
could hit `--exec`; `"--"` end-of-options added in all 3 yt-dlp argv
builders, regression-tested) + zip-slip guard on model-archive extract;
**Transcribe-tab time range** (#28) — clip_timestamps through the worker,
end-to-end verified (transcribed only 120–180s of a 10-min file, original
timeline, progress→100%); **multi-site download error visibility** — the
queue now shows yt-dlp's real ERROR line + a "Cookies from browser" hint
for login-walled sites (Facebook); **ffprobe "N/A"** tolerated;
**progress %% kept visible** during the startup marquee; a contributed
**hub_folder/model_path** fix (collaborator commit 5b59fbc).

### Still pending (next session)
- **#37 worker cancel/pause/checkpoint — DONE in v1.3.5.** A cooperative
  control channel now delivers cancel/pause/resume to the running worker
  (a `worker-stdin` reader thread flips the in-flight task's flags); pause
  truly halts, resume continues, and cancel flushes a resumable checkpoint
  instead of killing the worker. Proven by `tests/core/test_worker_control.py`
  + `tests/core/test_cancel_checkpoint.py` + `tools/e2e_cancel_pause.py`.
  Residual (NOT addressed): `ensure_worker_ready(headless=True)` could
  still deadlock if ever called on the Tk main thread — low risk (the
  headless path is only invoked off the main thread today).
- **Resource leaks — RESOLVED 2026-05-29 (deep audit, see §0.1).** Worker/
  yt-dlp now tree-killed via `core/_proc.py` (no orphaned ffmpeg/demucs);
  `partials/` swept at startup + cleared on declined crash-resume;
  HistoryDB closed in on_exit; demucs cache bounded; recorder streams to
  disk. Commits `cd402c9` + `7c91285`.
- **#38 selector tuning** — the download selector already falls back to a
  combined stream (`/best`) so it isn't YouTube-locked; the real fix
  shipped is the ERROR SURFACING. Once a user retries Dailymotion on
  v1.3.2 and the queue shows the actual error, fix that specific cause
  (don't change the selector blind — risks the proven YouTube path).
- **burn_subs filter escaping — RESOLVED 2026-05-29 (deep audit, see §0.1).**
  Subtitles now burn from a temp copy with a graph-safe ASCII name, so
  `' [ ] , ;` in a (downloaded) title can't break/inject the ffmpeg filter
  graph; the colon-escape is gated to Windows. New `tests/core/test_burn_subs.py`.
  Commit `0204cc8`.

### What shipped in v1.3.1 (PUBLISHED 2026-05-25, now pruned from GitHub)

Reliability bug-hunt on top of v1.3.0 (traced each UI action through the
code + four parallel audit agents). Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.3.1.md`. Headlines: **non-ASCII filename downloads
now transcribe** — yt-dlp stdout forced to UTF-8 (`_utf8_subprocess_env`)
PLUS a self-healing fallback (`DownloadService._recover_saved_path`) that
finds the real downloaded file if the parsed path is wrong; **language
codes normalized on the DEFAULT path** (`_normalize_language` now in
`_build_transcribe_kwargs`, not just the alt-backend call — fixes "en-US"
and multi-value picker codes like "zh-Hans,zh-CN" crashing the worker);
**VLC found via registry/Program Files** with a clear 64-bit hint
(`_locate_vlc_dir`); **download cancel stops the linked transcription** +
**re-run keeps the time-range**; **optional-dep probes catch OSError**
(diarization/parakeet/whisper_cpp no longer crash the app on a bad native
DLL — VLC bug class); Transcribe **path validation**; demucs via
`sys.executable`. Plus the queue **"working" marquee** animation and the
**0:00:00 time-range defaults**. New tests: test_normalize_language,
test_recover_saved_path, test_transcribe_kwargs, test_progress_cell
(+marquee).

### Still pending (next session)
- **#28 — time-range for the Transcribe tab**: let the user transcribe
  only a slice of a long local file. Recommended approach: faster-whisper
  `clip_timestamps` threaded through `_build_transcribe_kwargs` (the
  central kwargs builder), with the per-segment progress % computed
  relative to the clip bounds (transcriber.py:~1123) so the bar still
  fills 0→100. Add Start/End fields to the Transcribe tab + clip_start/end
  on TranscriptionTask.
- **Minor**: `watched_folder` has no `_drive_is_mounted` deferral like
  download_folder/model_path, so a not-yet-mounted/temp watched folder is
  silently dropped at launch (app/app.py watched-folder branch). Low
  urgency (degrades gracefully, just doesn't watch).

### What shipped in v1.3.0 (published 2026-05-25, now pruned from GitHub)

UX + reliability on top of v1.2.0. Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.3.0.md`. Headlines: **fixed auto-transcribe after
a merged video+audio download** (the saved-path parser matched the
yt-dlp-deleted audio fragment, so Shorts / reels silently failed to
transcribe — now `select_saved_path` makes the merged file win); per-row
**graphical progress bars** in both queues (`progress_cell`); the
**version is now visible** (window title `_base_title` + a version-stamped
installer shortcut via a `#define MyAppVersion` knob); the **Download row
shows "transcribing" + live progress** after an auto-transcribe (linked
via `TranscriptionTask.source_download` ↔
`VideoDownloadTask.transcription_task`, flipped back in `finish_task`);
the **"Last result" card** no longer expands to fill the Transcribe tab;
and the **language picker resets to "Auto" every launch** (no longer
persisted; other prefs still are).

### What shipped in v1.2.0 (published 2026-05-25, now pruned from GitHub)

UX + accessibility on top of v1.1.0. Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.2.0.md`. Headlines: app-wide copy/paste fix
(layout-independent Ctrl+C/V/X/A + right-click menus on every text field
+ a copyable log console), bulk multi-select queue actions (cancel /
re-run / resume / remove), auto-hiding queue scrollbars, model
download-status + a "Download now" button, "Open file" for finished
downloads, output-file de-dup (`name (1).srt`), the About dialog showing
the live version, and a stable installer `AppId` (single Add/Remove
entry that upgrades cleanly).

### v1.1.0 changes (folded into the published v1.2.0; v1.1.0 itself pruned)

Audio-in-downloads fix, the main-thread model-load freezes (download /
crash-resume / watched-folder), model-hub + download-folder persistence,
crash-resume nag, truncated-SMTV-download, About repo-URL removal, and
the opt-in "Cookies from browser" feature. Bug-hunt method + findings:
`docs/AUDIT_2026-05-25_boundary_bugs.md`.

## 2. Shipped deliverables — Standard + Portable (both embed-based)

Two published assets per release, both built from the slim
`embed_build\` tree (embeddable CPython 3.11 + deps):

| Asset | Local path | Size (v1.3.4) | Notes |
|---|---|---|---|
| Setup-Standard | `dist_installer/WhisperProject-v1.3.4-Setup-Standard.exe` | 219 MB | installs to Program Files (admin), shell-extension + shortcuts |
| Portable | `dist_installer/WhisperProject-v1.3.4-Portable.zip` | 326 MB | `shutil.make_archive` of `embed_build\`; extract + run `Run Whisper Project.bat`, no install |

History: v1.0.3 shipped a PyInstaller Portable EXE; 2026-05-24 the policy
was "Standard only"; **the user then asked for Portable back as a ZIP of
the embed tree (v1.3.2+).** Both ship now. The PyInstaller Compact
(`whisper_project_onedir.spec` + `installer.iss`) and onefile Portable
(`whisper_project_onefile.spec`) pipelines remain maintained-but-unshipped
(keep their hidden-import lists current so they don't bit-rot).

Download from:
**[github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)**

## 3. RELEASES — v1.3.6 latest, DONE (2026-05-26).

**v1.3.6** is live (Video Tiling tab + Linux/macOS groundwork; Standard
219 MB + Portable 326 MB). The step log below is from v1.3.4 and documents
the identical pipeline (bump → build → compile → zip → e2e → publish).

**Release policy (2026-05-26 owner — reverses the 2026-05-25 keep-all):**
- **Keep ONLY the latest release.** After publishing vNEW, DELETE the older
  release objects (`gh release delete vX.Y.Z --yes` — keeps the git tag +
  the local `dist_installer/` installer as backup). Only the latest + the
  separate `basic-v0.1.0` stay on the Releases page. (So step 7 below now
  means "prune the previous release," the opposite of before.)
- **Release LESS often** — batch several features/fixes per version
  (owner: "half or a third the speed"); don't cut a version per small change.
- **Push in batches** — commit locally often, push several commits together.

---

v1.3.4 was live on GitHub (Standard + Portable). Steps that ran:

1. ✅ Gate green: pyright `app/ core/` 0/0/0; hermetic suite (tests/ minus
   tests/smoke) exit 0.
2. ✅ Slim embed rebuild (`build_embed_installer.bat`, now prunes the
   heavy libs) — `embed_build\` = **805 MB** (was 1.6 GB), "embed_import_ok"
   + "build complete". Verified: torch/stable_whisper/whisper absent,
   faster_whisper present, `optional_deps.is_available("alignment"/"whisper_backend")`
   both False (on-demand path live).
3. ✅ Standard installer compiled clean (290 s) →
   `dist_installer\WhisperProject-v1.3.4-Setup-Standard.exe` (**219 MB**,
   size-stable + MZ magic). IMPORTANT: ISCC writes the EXE incrementally —
   wait for the "Successful compile" line / a stable size before publishing
   (a mid-write EXE looks smaller and ships corrupt). Here the background
   task exited 0 AND printed "Successful compile", so the size was final.
4. ✅ Portable ZIP via `embed_build\python\python.exe -c "shutil.make_archive(...)"`
   → `dist_installer\WhisperProject-v1.3.4-Portable.zip` (**326 MB**,
   testzip OK, has `Run Whisper Project.bat` + `gui.py`, no torch).
5. ✅ Past-bug E2E on the slim embed tree (`tools/e2e_slim_pastbugs.py`,
   run with the embed python) — drives the REAL worker over JSON stdin/
   stdout and asserts every output format lands. PASS: docx (36954 B, valid
   PK magic) + srt + json + txt all written; `en-US` normalised to `en` (no
   crash); clip 0–20s produced output (progress→100); apostrophe+space
   filename round-tripped.
6. ✅ Published — `gh release create v1.3.4 <Standard.exe> <Portable.zip>
   --target chore/cleanup-hardening --notes-file docs/RELEASE_NOTES_v1.3.4.md`;
   both assets `state=uploaded`, sizes match local.
7. ✅ Pruned v1.3.3 (`gh release delete v1.3.3 --cleanup-tag --yes`) —
   GitHub now has only `v1.3.4` + `basic-v0.1.0` (archive tags kept).
   **POLICY CHANGE (2026-05-25): this was the LAST prune.** Right after
   v1.3.4 shipped the user said "از این به بعد نسخه‌های قدیمی را پاک نکن" —
   do NOT delete old releases going forward. Future releases publish the
   new version and **leave every prior release + tag in place**. (The
   pruned v1.3.3 local artefacts still sit under `dist_installer/` if the
   user ever wants v1.3.3 re-published.)
8. **GUI-manual checks for the user** (not automatable): pick docx in
   Advanced settings → confirm a .docx lands next to the media; select
   Word-timestamp alignment → confirm the on-demand download prompt appears
   (and works) on a machine without torch; the Download-tab position slider;
   a non-YouTube / login-walled download (the queue shows the real error +
   cookie hint).

**To cut the NEXT release** (vX.Y.Z), bump the version in
`core/__init__.py` + `pyproject.toml` + both `.iss` files (the embed
`.iss` reads `#define MyAppVersion`), then repeat steps 1–7 — and step 7
now means **prune the previous release** (`gh release delete` the old one,
keep only the latest + `basic-v0.1.0`). Use absolute
paths via `cmd.exe` (a background cmd may not inherit cwd); `<REPO>` =
`C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2`.
Full step-by-step lives in `docs/RELEASE_PROCESS.md`.

### Deferred bug-audit items (`docs/AUDIT_2026-05-25_boundary_bugs.md`)
- SMTV cancel-latency on a stalled socket + no-retry; a site-layout
  change silently empties the article transcript.
- Worker-lifecycle: ~~`_pending_load_*` dangle if the awaited worker
  dies~~ **RESOLVED 2026-05-29** (Batch C [1], commit `f2c2991`): the
  loading modal now closes on startup_error/worker_exit and the pending
  state is cleared. STILL OPEN: `startup_error` still `stop_all()`s ALL
  workers + clears `app.workers`, not just the failing one (low impact —
  usually only one worker exists at first-transcribe; left for a targeted fix).
- Download rows stuck `interrupted` skew `stats()`.
- Hardware-probe stall (async attempt was REVERTED — a real fix needs
  `test_hardware_wizard_constructs_without_crashing` made async-aware).
- **Class C — needs a REAL yt-dlp + ffprobe harness before changing:**
  `--download-sections` keyframe snap (clip starts early), sub-second
  timecode, open-left `*-MM:SS` bound. Do NOT "fix" these blind.
- Older: P1s in `docs/STABILITY_AUDIT_2026-05-23.md`; SMTV server-side
  time-range slicing (limitation in `docs/integrations/smtv-brief.md`).

## 4. Branch + tag map

```
origin/master                       ← THE single branch; HEAD; carries v1.3.5
  tag v1.3.5                        ← the current release commit
  tag v1.3.4, v1.3.3                ← kept (releases are never pruned)
  tag v1.0.3                        ← earlier release commit (7295872)
  tag archive/cleanup-hardening-final ← old chore/cleanup-hardening tip (= master now)
  tag archive/basic-edition         ← old basic-edition tip (998 tests + downloads)
  tag archive/master-pre-merge      ← old (pre-2026-05-25) master Session-9 lineage
  tag archive/release-v0.7-baseline ← pre-orphan snapshot (recovery aid)
  tag v0.7.1, v0.7.0                ← historical releases
```

master's current history is the former `chore/cleanup-hardening` orphan
lineage (a squashed base + the v1.0.3 → v1.3.5 commits) — that's the
preserved project progress. The superseded pre-merge master (Session-9
era) and the deleted branches all live on as the `archive/*` tags above,
so nothing was lost.

## 5. The 1-line restart prompt

```
Read docs/SESSION_HANDOFF_NEXT.md first, then continue on master (the single mainline). Normal pushes to master are fine; don't force-push / rewrite master and don't move or delete published release tags (v1.0.3+ are public) without an explicit ask.
```

## 6. Forbidden actions (durable; mirrors CLAUDE.md)

- Don't `git push --force` / rewrite history on `master` (without an
  explicit ask) — normal pushes are fine now that master is the mainline
- Don't move or delete a **published release tag** (`v1.0.3`+ are public;
  moving them invalidates downloaded artefacts)
- Prune old GitHub releases — keep ONLY the latest + `basic-v0.1.0`
  (2026-05-26 owner; reverses the 2026-05-25 keep-all). Release less often;
  push commits in batches.
- Don't touch `.git/config`
- Don't code-sign the EXE

## 7. Sanity-check commands for the next session

```cmd
cd C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2
git log --oneline -5
git status
pyright app/ core/
python -m pytest tests/ --ignore=tests/smoke
```

Expected: the full hermetic suite passes (exit 0), pyright 0/0/0,
working tree clean. Optionally re-run the slim-build release gate
`embed_build\python\python.exe tools\e2e_slim_pastbugs.py` (PASS) after a
rebuild.

## 8. Key documents

| Doc | Purpose |
|---|---|
| [README.md](../README.md) | Project overview + install + config |
| [docs/INSTALL.md](INSTALL.md) | End-user install steps |
| [docs/BUILD.md](BUILD.md) | Two shipped build pipelines + the unshipped Compact one |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | Process model + threading |
| [docs/CONFIG.md](CONFIG.md) | Every config key documented |
| [docs/DEEP_AUDIT_BRIEF.md](DEEP_AUDIT_BRIEF.md) | Senior-architect line-by-line audit + fix brief for a fresh session |
| [docs/RELEASE_PROCESS.md](RELEASE_PROCESS.md) | How to ship the next release |
| [docs/RELEASE_NOTES_v1.3.5.md](RELEASE_NOTES_v1.3.5.md) | v1.3.5 user-facing notes (latest) |
| [docs/CHANGELOG.md](CHANGELOG.md) | Full version history |
| [docs/STABILITY_AUDIT_2026-05-23.md](STABILITY_AUDIT_2026-05-23.md) | Multi-day stability audit + the P1 punch list |
| [CLAUDE.md](../CLAUDE.md) | Durable rules for any Claude Code session |
