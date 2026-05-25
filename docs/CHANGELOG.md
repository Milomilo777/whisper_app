# Changelog

All notable changes to this project. Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.3.2] — 2026-05-25

Security + features release. A dedicated security/concurrency/resource
bug-hunt (four more parallel audit shards) plus the most-requested
feature.

### Added

- **Transcribe a time-slice of a file.** The Transcribe tab now has
  Start / End fields (default 0:00:00 = whole file), so you can transcribe
  e.g. 5 minutes out of a 10-hour recording. Segment timestamps stay on
  the original timeline.

### Security

- **yt-dlp option injection closed.** A pasted "URL" beginning with "-"
  was handed to yt-dlp without a "--" end-of-options separator, so it
  could be parsed as a flag (e.g. `--exec` → command execution) — and the
  format probe fires on paste. All three yt-dlp argv builders now insert
  "--" before the URL.
- **Zip-slip guard** on model-archive extraction: members that would
  resolve outside the cache dir are now rejected.

### Fixed

- **Failed downloads now say WHY.** Instead of "yt-dlp exited with code
  N", the queue shows yt-dlp's real error line; for login-walled sites
  (Facebook / Instagram) it adds a hint to enable "Cookies from browser"
  in Advanced settings.
- **Progress percentage stays visible during start-up.** The "working"
  animation kept the number (it had briefly hidden it behind a moving
  bar), so you can always see how far along a transcription is.
- **Corrupt-but-readable media** (ffprobe reports "N/A" duration) no
  longer aborts the run with an opaque error — it transcribes anyway.
- **Model-path fix when a hub folder is selected** (contributed).

## [1.3.1] — 2026-05-25

Reliability release — a focused bug-hunt (tracing each UI action through
the code, four parallel audits) on top of v1.3.0.

### Fixed

- **Auto-transcribe after a download silently produced no transcript when
  the title had a non-ASCII character** (apostrophe, accent, emoji, CJK).
  yt-dlp wrote stdout in the Windows code page, so the saved path came back
  mojibake'd and didn't match the real file. Now forces UTF-8 output, plus
  a **self-healing fallback** that finds the actual downloaded file when
  the parsed path is wrong — so even an unheard-of character can't lose the
  transcript.
- **Picking a non-English language crashed transcription with no output.**
  A region tag ("en-US") or a multi-value picker code ("zh-Hans,zh-CN",
  "pt,pt-BR,pt-PT", "he,iw") was passed straight to faster-whisper, which
  rejected it. Language hints are now normalized to a base ISO code on
  every transcription path.
- **The viewer said "VLC isn't installed" when VLC was installed.** It now
  locates VLC via the registry / Program Files, and the message spells out
  that a 64-bit VLC is required (a 32-bit VLC can't load into the 64-bit
  app).
- **Cancelling a download that had moved on to transcribing** left the
  transcription running and silently undid the cancel; **re-running a
  time-range download** fetched the full video. Both fixed.
- **Optional features no longer crash the app on probe.** Speaker
  diarization / alternate engines that fail to load a native library now
  just show as unavailable instead of taking the app down.
- **The Transcribe tab rejects a missing / mistyped file** with a clear
  message instead of failing deep in the worker.

### Added

- **An animated "working" bar** in the queue while a task is starting up
  (model load) so it's clear something is happening before the percentage
  begins.
- **The download time-range Start / End fields are pre-filled with
  0:00:00** so they're easier to edit (leaving both = the full video).

## [1.3.0] — 2026-05-25

UX + reliability release on top of v1.2.0 — bug fixes and visibility
improvements found while running the app on real downloads.

### Added

- **Graphical progress bars in the queue rows.** The transcription and
  download queues draw a block bar (e.g. `████░░░░░░ 42%`) next to the
  number, so progress is visible at a glance instead of just a figure.
- **The version is visible.** The window title shows `Whisper Project
  v1.3.0`, and the Standard installer's Start-menu / desktop shortcut is
  named with the version — so you can tell which build is installed.
- **The Download tab shows transcription progress.** After an
  auto-transcribe-from-download, the download row reads "transcribing"
  and mirrors the live transcription progress, then flips to "finished",
  so a slow transcription no longer looks like a stalled, idle 100%.

### Changed

- **The "Last result" card no longer dominates the Transcribe tab** — it
  sizes to its content instead of expanding to fill the lower half.
- **The transcription language resets to "Auto" on every launch** and is
  no longer persisted; every other transcribe preference is still saved.

### Fixed

- **Auto-transcribe after a video+audio download.** yt-dlp merges the two
  streams into one file and deletes the per-stream fragments; the
  saved-path parser had been matching the now-deleted audio fragment, so
  auto-transcribe hit "No such file or directory" and silently did
  nothing. It now resolves the merged output (and the
  already-downloaded / extracted-audio cases too). Seen on Facebook reels
  and YouTube Shorts.

## [1.2.0] — 2026-05-25

UX + accessibility release on top of v1.1.0 — mostly things the operator
hit while using the app on a Persian keyboard.

### Added

- **Copy / paste works everywhere now** — a right-click menu (Copy / Cut
  / Paste / Select all) on every text field, plus a copyable log console
  (right-click → Copy / Copy all / Clear). Mouse-driven, so it never
  depends on the keyboard layout.
- **Bulk queue actions.** Select multiple rows in the transcription or
  download queue and Cancel / Re-run / Resume / Remove them all at once.
- **Scrollable queues.** Both queue lists get an auto-hiding vertical
  scrollbar that appears only when the list outgrows the visible area.
- **Model visibility + on-demand install.** The Advanced model picker
  marks each model "downloaded" / "needs download", and a "Download now"
  button installs the selected model without starting a transcription.
- **Open file from the Download tab** — a finished download's context
  menu can open the media file directly (not just its folder).

### Fixed

- **Clipboard shortcuts under a non-Latin keyboard layout.** Ctrl+C / V /
  X / A keyed off the Latin keysym, so copy/paste/cut/select-all were
  dead while a Persian (or Arabic, Russian, …) layout was active. They
  now dispatch by physical keycode.
- **Transcript outputs no longer overwrite a previous run** — a re-run
  writes `name (1).srt` / `name (1).json` (a shared index) instead of
  clobbering the earlier files.
- **The About dialog** shows the live app version (it was hard-coded to
  an old number) and opens in one click (it used to be a menu whose only
  item was another "About").

## [1.1.0] — 2026-05-25

Maintenance release — bug fixes plus one opt-in feature. Restores audio
in video downloads, removes several UI freezes and nags, makes the
model-hub and download-folder choices stick, fails a truncated SMTV
download instead of shipping a corrupt file, and adds browser-cookie
support so login-walled sites (Facebook / Instagram / TikTok stories,
age-gated YouTube Shorts) can download.

### Added

- **Download from login-walled / age-gated sites via browser cookies.**
  A new "Cookies from browser" picker in Advanced → Downloads passes
  yt-dlp's `--cookies-from-browser`, so Facebook / Instagram / TikTok
  stories and age-restricted YouTube Shorts can download using your
  logged-in browser session. Off by default; pick your browser
  (Chrome / Edge / Firefox / …) to enable.

### Fixed

- **Video downloads were silent (no audio).** yt-dlp's format selector
  was emitted as `video…/bestvideo+audio…/best` without grouping, so
  yt-dlp's `/` precedence selected a video-only stream and the merged
  file had no audio. Each stream group is now parenthesized:
  `(video…)+(audio…)/best`.
- **Model-load froze the UI on several paths.** Three main-thread
  enqueue paths — auto-transcribe-after-download, crash-resume
  ("Resume interrupted transcriptions?" → Yes), and the watched
  folder — waited synchronously for the Whisper model to load (up to
  the 120 s timeout), freezing the whole app. They now share one
  non-blocking helper that spawns the worker and polls for readiness
  with `after()`, so the UI stays responsive and the task is queued
  once the model is ready.
- **The model hub folder you picked was ignored.** A `model_path`
  derived from the *default* hub during startup was being written to
  `config.json`, then treated on the next launch as an explicit
  per-model override that outranked your chosen `hub_folder` — so the
  model always loaded from `<app>/hub` and `model_path` looked like it
  "reset" every launch. Auto-derived model paths are no longer
  persisted; a genuinely custom path is still kept.
- **The crash-resume prompt reappeared on every launch.** Declining
  "Resume interrupted transcriptions?" left the rows flagged
  `interrupted`, so the same prompt returned next time. Declining now
  clears the flag on the offered rows; genuine future crashes still
  prompt.
- **A download folder on a removable / network drive was forgotten.**
  If the drive was detached at launch, the folder was cleared *and the
  cleared value was written back to config*, so the choice was lost
  permanently. The cleared value is no longer persisted while the drive
  is merely unmounted — the folder returns when the drive does. (Same
  class as the `model_path` fix above.)
- **A truncated Supreme Master TV download was treated as success.** If
  the CDN dropped the connection mid-transfer, the partial file was
  renamed to the final name and auto-transcribed — a clean-looking but
  corrupt result. The download now fails and reports an error when fewer
  than the advertised (Content-Length) bytes arrive.

### Changed

- The **Advanced settings** dialog is now resizable and scrolls, so it
  fits on smaller screens.
- The **About** dialog no longer shows the source-repository URL.

## [1.0.3] — 2026-05-23

UX + memory release. Adds the optional time-range download
collaborators asked for and changes the model-load policy so
idle launches don't pay for ~2 GB of RAM the user may never use.

### Added

- **Time-range video download.** New optional Start / End fields
  on the Download tab. Fill either (or both) in `H:MM:SS`,
  `MM:SS`, or seconds, and yt-dlp's `--download-sections`
  fetches only that slice. The Queue row label shows a
  `trim 0:51 → 1:25` badge so it's obvious which jobs are
  partial. The transcribe step naturally runs proportionally
  faster — most of the savings come from the smaller audio,
  not the smaller download. Supreme Master TV URLs are not
  sliced in this release (the SMTV scraper has no slicing path);
  one clear WARN log line + a known-limitation note in
  `docs/integrations/smtv-brief.md`.
- **Lazy Whisper-model load.** The app no longer preloads the
  3 GB Whisper model on launch. Idle RAM drops by ~2 GB.
  The first transcribe of a session shows a modal "Loading
  Whisper model…" dialog with an indeterminate progressbar; the
  worker spawns and loads, the dialog dismisses, the transcribe
  proceeds. Subsequent transcribes reuse the alive worker — only
  the first one pays the load. Crash-resume and watched-folder
  enqueues go through the same gate without showing a modal
  (headless mode, 120 s timeout).

### Changed

- `App._on_start` no longer calls `start_standby()`. The method
  is kept as a deprecated proxy for backwards compatibility with
  any test that still calls it.

### Documentation

- `docs/integrations/smtv-brief.md` — added the time-range
  limitation note.

### Shipped artefacts

Same shape as v1.0.2: Portable + Setup-Standard only. The
Compact pipeline still exists in the repo + still builds, but no
Compact EXE is published.

## [1.0.2] — 2026-05-23

Reliability + UX release. Closes the long-uptime + multi-hour-file
gaps the 2026-05-23 stability audit catalogued, and lands the
resume-from-cancellation feature.

### Added

- **Resume from cancellation / pause / crash.** The transcribe
  loop now writes a periodic checkpoint
  (`%LOCALAPPDATA%/WhisperProject/partials/<sha1>.json`) every 10
  segments or 20 s. Cancelling, pausing or crashing keeps the
  checkpoint on disk; a new Resume command on cancelled rows
  slices the source audio from the last segment boundary,
  transcribes only the remainder, merges with the already-done
  segments, and runs the post-pipeline (diarisation, chapters,
  alignment, voiceprint) on the full merged result. faster-whisper
  backend only; whisper.cpp and Parakeet fall back to a fresh
  re-run with a clear log line. Validates source mtime/size and a
  config fingerprint before resuming, so a changed file or model
  silently starts fresh instead of producing garbage.
- **Pause command in the queue right-click menu** for running
  tasks. The engine already supported `task.paused`; the menu
  entry was the only missing UI surface.
- **About dialog feature inventory.** The previous one-line
  `messagebox.showinfo` is replaced by a scrollable Toplevel
  listing every capability of the app grouped into nine
  sections — Transcription engine, Output formats,
  Post-processing, Video download, Transcript viewer, Workflow
  + system integration, Search + statistics, Keyboard shortcuts,
  Privacy. Many capabilities ship enabled by default but live
  behind the Advanced dialog with no main-UI surface; this
  dialog is the canonical "what does this app actually do"
  reference.

### Fixed

- **3 GB re-download on the launch after the first-run hub picker.**
  (Originally fixed in v1.0.1; carried forward.) The hub-folder
  dialog was asynchronous and the worker spawned with an empty
  `hub_folder`, downloading the model to a path the next launch
  wouldn't resolve to. Aligned the empty-hub fallback in
  `_apply_runtime_fallbacks` with the dialog's default and
  deferred `start_standby()` until the dialog answers.
- **Worker liveness watchdog kills diarisation on long files.**
  `_run_post_pipeline` now plumbs `progress_cb` into
  `diarization.diarize`, mapping sherpa-onnx's 0..1 tick into the
  90..99 percent slot. Bumped `LIVENESS_TIMEOUT_S` from 30 s to
  120 s as defence in depth.
- **Same watchdog pattern in four more silent C calls.** New
  `core/_liveness_tick.py` context manager wraps
  `stable_ts.model.align(...)`, the Demucs CLI subprocess, the
  Parakeet `decode_stream(...)` call, and the whisper.cpp
  `model.transcribe(...)` call. Without this, every alt-backend
  transcription and every alignment / Demucs run on slow CPU was
  one watchdog tick away from a mid-flight kill.
- **`.whisperproject.json` overrides leak across files.**
  `_apply_runtime_overrides` mutated the module-level config in
  place. The long-lived worker carried a folder-A override into
  folder-B's files. Now wrapped in `_runtime_overrides_scope`
  which snapshots and restores touched keys around each file —
  with eight regression tests.
- **`tk.after(0, ...)` from background threads.** On Python 3.14
  this raises `RuntimeError`; on earlier 3.x it's undefined and
  the existing `try/except: pass` blocks silently dropped the
  callback. Added an `App._main_thread_calls` queue + drainer +
  `post_to_main(fn)` helper; rerouted burn-subs, hardware-wizard
  benchmark, and tray-click callbacks through it.
- **Demucs temp-directory leak.** `tempfile.mkdtemp(...)` in
  `core/separator.py` was never removed on the success path,
  leaking 30–50 MB per separation. Cleanup now lives in a
  `finally:`.

### Documentation

- `docs/STABILITY_AUDIT_2026-05-23.md` — 26-item audit driven by
  the diarisation-watchdog bug. 7 P0 / 9 P1 / 10 P2 with
  file:line + symptom + suggested fix. P0s plus the
  highest-leverage P1 are closed in this release; the rest are
  the next-session punch list.

### Shipped artefacts

This release skips the Setup-Compact installer (Portable +
Setup-Standard cover the same audiences). Two EXEs uploaded to
the v1.0.2 release page.

## [1.0.1] — 2026-05-23

First stable release. Marks the project as feature-complete + freeze-ready
after an audit-driven hardening sweep (~62 of 72 audit items closed, the
rest deferred with documented rationale), plus a pre-ship fix for a
fresh-install model re-download race caught during verification.

### Fixed

- **3 GB re-download on the launch after the first-run hub picker.**
  On a fresh install the first-run hub-folder dialog was asynchronous:
  it opened, returned the default path immediately, and `_on_start`
  fired `start_standby()` while the user was still reading the
  dialog. The worker then computed `model_path` from an empty
  `hub_folder` and downloaded the model under
  `%LOCALAPPDATA%\WhisperProject\Cache\models\`. When the user
  accepted the dialog default (`<app_dir>\hub`), the next launch
  resolved `model_path` to a directory the model was never
  extracted into, triggered a `startup_error`, and re-downloaded
  the full 3 GB archive. Fixed by:
    * Aligning the empty-hub fallback in
      `_apply_runtime_fallbacks` with the dialog's default
      (`default_hub_folder()`), so accepting the default is a no-op
      for the model location.
    * Deferring `start_standby()` in `App._on_start` until the hub
      dialog's `on_done` callback fires, so the worker starts with
      the user's actual choice even when they pick a custom folder.
  Regression test added in `tests/core/test_hub.py`.

### Added — v0.8 Phase 1 (Shards A + B)

- **Hallucination detector** — flags suspect Whisper segments via
  three signals: Bag-of-Hallucinations wordlist, 1/2/3-gram
  repetition, and (optional) VAD-disagreement. Annotates JSON with
  `seg["suspect"] = True` + `suspect_reason`. Transcript viewer
  highlights flagged rows in red. Toggle:
  `hallucination_detect_enabled`.
- **Multi-model picker** — Large v3 (default), Large v3 Turbo, and
  Distil Large v3.5 selectable from the Advanced dialog. Slug-keyed
  registry; existing config keeps working unchanged.
- **Hardware autodetect wizard** — probes CUDA → QNN/NPU → OpenVINO
  → DirectML → CPU int8, persists the choice in `hardware.json`,
  re-validates at every model load.

### Added — v0.8 Phase 2 (live + AI layer foundations)

- `core/recorder.py` — mic + WASAPI loopback recorder.
- `core/llm.py` — local LLM panel (Qwen2.5-1.5B, download-on-first-use).
- `core/separator.py` — Demucs vocal-separation pre-process.

### Added — v0.8 Phase 3 (data + recognition expansion)

- `core/backends/parakeet.py` — sherpa-onnx Parakeet TDT v3 backend.
- `core/search.py` — semantic + FTS5 search across saved transcripts.
- `core/chapters.py` — auto-chapter markers via long-silence heuristic.
- `core/voiceprint.py` — cross-file speaker fingerprint DB.

### Added — Model Hub Folder feature

- First-run dialog asks where to store Whisper model files; choice
  is persisted to `config.json` under `hub_folder`. Default
  suggestion: `<app>/hub`. Inno Setup uninstaller asks whether to
  delete out-of-tree hub folders.

### Hardened — audit-driven (R-series)

- WAL journal mode + integrity check on `history.db` (crash-safe).
- Worker IPC: per-worker UUID session token + 5 s heartbeat + 30 s
  liveness watchdog. stdin writes moved off Tk thread. History row
  inserted BEFORE dispatch.
- Structured 4-step worker shutdown (stdin → wait → terminate → kill).
- INFO logs at every device / backend / model decision point.
- `--safe-mode` CLI flag: backs up `config.json` aside, fires fresh
  first-run dialog.
- `safe_thread` helper: every daemon thread now logs uncaught
  exceptions with full stack trace.

### Tests

535 unit + integration tests (+260 from 0.7.x baseline of 275).
10/10 real-file end-to-end against the SMTV reference clip. 7/7
smoke + end-to-end against the real Whisper model. pyright `app/
core/` 0 errors, 0 warnings, 0 informations.

### Documentation

- `docs/SENIOR_REVIEW_2026-05-21.md` — engineering audit
- `docs/EXECUTION_ROADMAP.md` — derived patch plan (35+ items)
- `docs/FINAL_FREEZE_AUDIT_2026-05-21.md` — pre-release sign-off
- `docs/RELEASE_PROCESS.md` — the ship sequence
- `docs/README.md` — navigation index for `docs/`
- `docs/roadmap/` — future-release research (v0.9 + beyond)

## [0.7.1] — 2026-05-20

Version bump packaging the Session-14 hands-off polish push, listed
in detail below under the original 0.7.0 history. Same source as the
final 0.7.0 build; rebranded so the three installer EXEs reflect the
new feature surface (backends, viewer enhancements, tray, …).

## [0.7.0] — 2026-05-20

### Added — Session 14 (hands-off polish from `HANDOFF_NEXT_SESSION.md`)

- **Filename templating** — `output_filename_template` config key is now honoured by every writer. Tokens `{base}`, `{ext}`, `{lang}`, `{date}`, `{speaker_count}` resolve at write time. Templates may include sibling subdirectories (`transcripts/{base}.{ext}`) — those folders are created on the fly. Malformed templates fall back to the legacy `{base}.{ext}` layout so a corrupt config never blocks a write.
- **Pluggable Whisper backends** — `core/backends/` houses an ABC plus two implementations. `faster_whisper` (default) preserves the CTranslate2 path with module-level `MODEL`/`PIPELINE` globals; `whisper_cpp` drives pywhispercpp on quantised ggml models (~1.1 GB for large-v3-q5_0). The Advanced dialog grows a backend picker and a "Download whisper.cpp model..." button.
- **Word-level alignment refinement** — `core/alignment.py` post-processes Whisper segments through stable-ts when `config["alignment"] == "stable_ts"`. Loads stable-ts's `tiny` Whisper model for the DTW alignment pass so word boundaries lock to ±50 ms.
- **Viewer enhancements (find/replace, speaker rename, fillers, confidence colours, karaoke)** — `Ctrl+F` opens a Find-and-Replace dialog with case-insensitive default + match-case toggle. Right-click on a segment with a speaker label → "Rename ... (everywhere)..." rewrites every same-labelled segment. Word-confidence colour coding (green ≥ 0.85, amber ≥ 0.6, red below) when segments carry `words` with probabilities. "Remove fillers" button strips `uh`/`um`/`er`/… with a whole-word regex. Karaoke wraps the active word in `[brackets]` in the side panel as VLC plays. `Ctrl+S` saves all edits atomically via `core.writers.json_writer`.
- **System tray + minimise-to-tray + native toast** — `app/widgets/tray.py` wraps pystray + Pillow on a daemon thread. Right-click menu: Show / Hide / Exit. Icon flips between a hollow blue ring (idle) and a filled red dot (active job). `config["minimise_to_tray"]` (opt-in) redirects `WM_DELETE_WINDOW` to hide-window. Completed transcriptions trigger `TrayController.notify(...)` so the user sees a native toast even when minimised.
- **High-DPI scaling** — `App._apply_hidpi_scaling()` reads `winfo_fpixels('1i')` at startup and computes Tk's scaling factor so fonts and paddings don't shrink to a 1 cm icon on 125 / 150 % Windows displays.
- **Anonymous opt-in telemetry** — `app/observability.py` is now gated on `config["telemetry_opt_in"]` (Advanced dialog checkbox). Sentry crash reporting requires that *and* `$SENTRY_DSN`; launch ping requires that *and* `$WHISPER_TELEMETRY_URL`. The ping carries `{os, version, python, anonymised_id}` only — `anonymised_id` is a SHA-256 of a one-shot UUID4 stored under `user_cache_dir()/telemetry_id`.
- **Auto-resume after crash** — `App._maybe_offer_crash_resume` runs on launch: if `history.db` flagged rows interrupted on the *previous* run and the source files still exist, prompts to re-enqueue them.
- **Per-folder `.whisperproject.json` overrides** — `core.config.merge_project_overrides` walks up from each transcribed file and overlays the closest `.whisperproject.json` on top of the global config. Dict-valued keys (`model`, etc.) deep-merge one level. Bad JSON / non-object roots are silently ignored.
- **Watched-folder UI wiring** — the existing `core.watcher.FolderWatcher` class is now wired through the Advanced dialog. New media files dropped into the configured folder are stability-checked (size stable for 1.2 s) then auto-enqueued via a Tk-safe `after()` hop. Stops/restarts cleanly when the user picks a new folder.
- **Windows Explorer "Transcribe with Whisper Project"** — both `installer.iss` and `installer_embed.iss` ship an optional shell-extension task (`shellext`) that writes the appropriate registry entries under `HKCR\*\shell\WhisperProjectTranscribe`. Hits the existing v0.7.0 CLI mode (`gui.py transcribe "%1"`).

### Added — Session 13 (gap-closing push)

- **Speaker diarization** via `sherpa-onnx` (no HuggingFace token). Toggle on the Transcribe tab. SRT / JSON / MD / DOCX writers all carry the speaker label. ONNX models live in `bin/diarization/` and ship with each installer.
- **In-app transcript viewer** (`Help → Open transcript viewer…`, plus "View transcript" button on the Last Result card). Segment table with type-as-you-search filter, double-click to seek, embedded `python-vlc` playback when libvlc is installed (falls back gracefully).
- **DOCX export** via `python-docx`. New binary-write path in `_write_outputs` with atomic `.part → os.replace` semantics preserved.
- **Markdown export** — stdlib only. Heading + per-segment timestamps + optional `_Speaker N:_` italics.
- **Drag-and-drop** (one or many files, or a URL) onto the window. Powered by `tkinterdnd2`; the App stays usable when the dep is missing.
- **Recent files submenu** populated from `history.db` (last 10 unique files). `File → Recent files`.
- **Window geometry persistence** — saves on exit, restores on next launch.
- **Multi-file Browse…** — selecting several files in the dialog enqueues them all.
- **Keyboard shortcuts** — `Ctrl+O` Browse, `Ctrl+Enter` Transcribe, `Esc` Cancel running, `Ctrl+Q` Exit.
- **GitHub Actions CI** (`.github/workflows/ci.yml`). Pyright + the unit suite on every push and PR. Matrix: Windows + Ubuntu, Python 3.11 + 3.12. Ubuntu wraps the pytest invocation in `xvfb-run`.

### Added

- **Session 12** — Three independent installation methods, all shipped from a single branch (`release/v0.7.0-installer-3-options`) on a single tag (`v0.7.0`):
  - **Method A — Portable** (`WhisperProject-v0.7.0-Portable.exe`, ~190 MB). PyInstaller `--onefile` build via `whisper_project_onefile.spec`. One file, no install, unpacks to `%TEMP%\_MEI*` per launch.
  - **Method B — Setup-Compact** (`WhisperProject-v0.7.0-Setup-Compact.exe`, ~137 MB). PyInstaller onedir from `whisper_project_onedir.spec` wrapped in `installer.iss` (Inno Setup 6, LZMA2 ultra). Real installer with Start Menu / desktop / Add-Remove-Programs entries.
  - **Method C — Setup-Standard** (`WhisperProject-v0.7.0-Setup-Standard.exe`, ~153 MB). Embeds a full `cpython-3.11.15+20260510-x86_64-pc-windows-msvc-install_only` distribution from [python-build-standalone](https://github.com/astral-sh/python-build-standalone), pip-installs `requirements.txt` into the bundle, copies the source tree, and wraps it via `installer_embed.iss`. Shortcuts launch `pythonw.exe gui.py`; the source is browsable on disk after install.
  - `build_embed_installer.bat` orchestrates the Method C tree.
  - All three pass `tests/smoke/test_exe_real_e2e.py::test_exe_worker_transcribes_real_video` on a clean install location with a real video, confirmed via the dual-launcher conftest fixture (`WHISPER_SMOKE_GUI` env var selects the embeddable-Python flavour).
- **Session 11** — Supreme Master TV download integration. New module `core/integrations/smtv.py` (stdlib only) scrapes any `/{lang}1/v/<id>.html` episode page for video qualities (1080p/720p/396p), the MP3 audio file, the article-text transcript, and the sibling-parts playlist; the Download tab automatically routes SMTV URLs through this module instead of yt-dlp. Sub-features:
  - **Series download.** When a multi-part episode is pasted, a "Download all parts of this series (SMTV)" checkbox appears (default ON) and enqueues one task per sibling part.
  - **MP3 audio mode.** SMTV serves real MP3 files directly; the Audio mode dropdown shows `MP3 (audio only)` and the download path skips ffmpeg entirely.
  - **Transcript persistence.** The page's article-text body is saved next to the media as `<base>.txt` (UTF-8). Auto-transcribe-after-download still runs unchanged on top, so users get two transcript surfaces — the site's editorial transcript and whisper's SRT/JSON.
  - 23 unit tests under `tests/integrations/test_smtv.py` against three HTML fixtures; 2 live-network smoke tests under `tests/smoke/test_smtv_smoke.py` (skipped offline). `docs/integrations/smtv-research.md`, `smtv-brief.md`, `smtv-acceptance.md` document the URL contract and SMTV-T1..T8 verification tokens.
- **Session 8** — `tests/smoke/` integration suite for the compiled exe. Three pytest files (`test_exe_real_e2e.py`, `test_app_headless.py`, plus a `conftest.py` with skip-guards for missing model / video / exe) and a `README.md` explaining why these tests have to live alongside the unit suite — packaging bugs are invisible from source-side. `test_exe_real_e2e.py` spawns `WhisperProject.exe --worker`, sends the actual JSON `transcribe` command, and asserts SRT + JSON land on disk; `test_app_headless.py` drives the Tk App in a withdrawn window through every service. Regression guards `test_exe_bundles_silero_vad_asset` and `test_exe_bundles_ffmpeg` lock in the Session 8 packaging fix.
- **Session 8** — `docs/SESSION_8_PACKAGING_FIX.md` documenting the silero_vad_v6.onnx packaging bug and why source-side tests didn't catch it.
- **Session 7** — `docs/architecture-diagrams.md` (Mermaid simple overview + SVG embed + pointer to prose ARCHITECTURE.md). Hyphenated filename to avoid a case-insensitive Windows clash with the existing `ARCHITECTURE.md`. The Mermaid view uses the same color palette as the SVG so the two diagrams feel related at a glance. README now links to it as the first "Project documentation" entry.
- **Session 7** — `docs/NEXT_SESSION_HANDOFF.md` — two-minute briefing for any future architect. Includes the current commit/branch/tag inventory, a 60-second orientation command list, the candidate phases ranked by impact-per-effort, the hard rules (single branch, no tokens, `bin/` ignored, Tk single-threaded, JSON protocol sacred), what's explicitly out of scope (Persian/Arabic, cloud LLMs, mobile, streaming), where to look when something feels weird, files not to touch, and a one-paragraph user prompt to start the next session.

### Fixed

- **Session 9** — `App.destroy()` now cancels every pending `tk.after()` callback before tearing down the Tcl interpreter. Previously, the service poll loops (`TranscriptionService.poll`, `FormatService.poll`, `DownloadService.poll`) reschedule themselves every tick; on shutdown those pending callbacks fired into a destroyed interpreter and spammed the log with hundreds of `invalid command name "<id>poll"` errors. Now the override iterates `tk.call("after", "info")` and calls `after_cancel` on each id before delegating to `super().destroy()`.
- **Session 9** — `core/transcriber.py:load_model_async` no longer swallows exceptions. The background-thread wrapper had a bare `except Exception: pass` that hid a real model-corruption case in the field for a whole session. Now it logs via `logger.exception` and forwards the message to `status_cb` if provided.
- **Session 9** — `core/transcriber.py:get_duration` now passes `timeout=60` and (on Windows) `creationflags=subprocess.CREATE_NO_WINDOW` to the bundled ffprobe call. A wedged ffprobe used to hang transcription indefinitely with no cancel, and the windowed exe popped a black console window for every probed file.
- **Session 9** — `messagebox.showinfo("About", ...)` now passes `parent=self` so the dialog centers on the app window instead of the screen.
- **Session 8** — `whisper_project.spec` now collects `faster_whisper`'s data files via `collect_data_files('faster_whisper')`. Without this, the compiled exe crashed the moment a user clicked **Transcribe** with VAD enabled (the default) because `silero_vad_v6.onnx` was absent from the bundle. The bug was invisible from `python gui.py` because source-side code resolves the asset from `site-packages/faster_whisper/assets/`. Only spawning the compiled `WhisperProject.exe --worker` and sending a real `transcribe` command exposed it. Now covered by the smoke suite — see Added above.
- **Session 8** — `whisper_project.spec` retains the Session 8a `contents_directory='.'` on the `EXE()` call so bundled `bin/` lands beside the exe, not inside `_internal/`. The `build.bat` xcopy fallback is no longer triggered on a clean build.

### Changed

- **Session 12** — `whisper_project.spec` renamed to `whisper_project_onefile.spec` to disambiguate from the new onedir variant. EXE `name=` field updated to `WhisperProject-v0.7.0-Portable`. `installer.iss` `OutputBaseFilename=` updated to `WhisperProject-v0.7.0-Setup-Compact`. Both .gitignore whitelist entries follow the rename.
- **Session 12** — `tests/smoke/conftest.py` and `tests/smoke/test_exe_real_e2e.py` gained dual-launcher support. The new `gui_script` fixture reads `WHISPER_SMOKE_GUI` and, when set, makes the worker subprocess launch as `[pythonw, gui.py, "--worker"]` instead of `[exe, "--worker"]` — required to verify Method C without writing a third smoke file.
- **Session 12** — `installer_embed.iss` carries a `[UninstallDelete]` block that sweeps `__pycache__` and the install subdirectories on uninstall. Inno Setup otherwise leaves Python's runtime-generated `*.pyc` files behind because they weren't recorded in the install manifest.
- **Session 12** — Repo cleanup: nine phase-acceptance plans + briefs + session writeups (PHASE_0/1/1B/2A/3A/NEXT acceptance, PHASE_1 brief, PHASE_NEXT brief, NEXT_SESSION_HANDOFF, SESSION_8_PACKAGING_FIX, SESSION_SINGLE_FILE_EXE, SESSION_DUAL_DELIVERABLE) moved into `docs/history/` to keep the active docs surface at-a-glance. README rewritten 190 → ~60 lines. BUILD.md rewritten to cover all three pipelines.
- **Session 11** — `app/services/format_service.py` and `app/services/download_service.py` now branch on SMTV URLs (`core.integrations.smtv.parse_episode_id` and a `kind: "smtv"` marker on the format dict) and bypass the yt-dlp probe / spawn entirely. No behaviour change for YouTube or any other URL.
- **Session 11** — Both PyInstaller specs (`whisper_project_onefile.spec` and `whisper_project_onedir.spec`) gain `core.integrations.smtv` in `hiddenimports` so the module survives onefile bundling and onedir-via-installer packaging.
- **Session 7** — `docs/MANUAL_STEPS.md` scrubbed: the `## A. Security` block that named two leaked GitHub PAT prefixes was removed. Sections re-lettered (B → A through H → G) so the file still reads cleanly. The Summary was rewritten to drop the "two human-required items" framing; there's now exactly one open human decision — which Phase to ship next.
- **Session 7** — `README.md` "Project documentation" footer now points at `architecture-diagrams.md` first, then the direct SVG link, then the prose ARCHITECTURE.md, so a new reader hits the visuals before the prose.

### Notes

- The leaked PAT prefixes still appear in this repo's history at commit `6d97a5f`'s diff. With the tokens revoked (which the user was asked to do; see Session 7's pending-actions note in `SESSION_LOG.md`), those strings are inert. Standard guidance for accidental-token-commit is "revoke + move on" rather than rewrite history; we followed it.

- **Session 6 research** — `docs/COMPETITIVE_ANALYSIS_2026.md` (~2900 words, ~40 cited sources). 2026 STT landscape scoped to EN + CJK + FR + DE (Persian/Arabic explicitly excluded). Covers Alibaba FunAudioLLM (SenseVoice / FunASR / CapsWriter), NVIDIA NeMo (Parakeet-TDT-0.6B-v3 / Canary-1B-v2), Whisper speedups (Insanely-Fast-Whisper / WhisperX / stable-ts / WhisperKit / Whisper-Streaming / WhisperLive / pywhispercpp), Tencent Covo-Audio, and 17 commercial products (Deepgram Nova-3, AssemblyAI Universal-3-Pro + LeMUR, ElevenLabs Scribe v2, Descript, MacWhisper 12, Apple Voice Memos iOS 18, etc.). Synthesizes 15 candidate features ranked by impact, Chinese-language gotchas (tokenization, punctuation, simplified/traditional, line-length, CPS), best-model-per-language matrix, and a five-feature Descript-style Phase 4 editor blueprint.
- **`docs/architecture.svg`** — 1500×1100 layered system diagram, color-coded by role (user / UI / core / subprocess workers / external processes / filesystem / test+build / external network). Drop shadows, dashed-for-async arrows, red "killer flow" callout for Phase 3a auto-transcribe-after-download. Renders inline on GitHub. Authored after four reflection passes.
- **`docs/ROADMAP.md`** restructured (Session 6) — new **Phase 6 — CJK polish + pluggable backends** with 8 sub-items: SenseVoice + Parakeet pluggable backends, Chinese punctuation post-processor (FunASR `ct-punc`), CJK-aware line splitting per Netflix style guide, simplified↔traditional via OpenCC, number/date normalization via cn2an, hallucination + repetition cleanup, stable-ts integration for word-perfect timestamps, sound-event tagging for SDH. Old Phase 6 (Hardening) renumbered to Phase 7 with no content loss. **Phase 4 (editor) rewritten** to drop the RTL Persian items (de-scoped — user audience is now 94% Chinese) and adopt the Descript-style blueprint: edit-back-to-subtitle with re-flowed timestamps, gap/silence panel, speaker labels with global rename, multilingual filler-word bulk operations (EN/FR/DE/ZH dictionaries) with dual caption-only vs. cut modes, CJK-aware subtitle linter.
- `README.md` documentation footer updated to point at `docs/architecture.svg` and `docs/COMPETITIVE_ANALYSIS_2026.md`.
- **Final compile** — `whisper_project.spec` (PyInstaller `--onedir`, deterministic, committed) + `build.bat` at the repo root with documented exit codes (0 success / 1 PyInstaller failure / 2 verification failure / 3 smoke launch failure). Build verifies the four required runtime files (`WhisperProject.exe` plus `bin/ffmpeg.exe`, `bin/ffprobe.exe`, `bin/yt-dlp.exe`) and falls back to a manual `xcopy` of `bin/` if PyInstaller's `datas` silently dropped it (which it does — caught on the first build). `docs/BUILD.md` documents modes, exit codes, the `bin/` fallback, and explains why `config.json` is intentionally not in `dist/` (Phase 1.2 placed it in `%LOCALAPPDATA%`). `.gitignore` now keeps the committed `whisper_project.spec` while ignoring stray local `.spec` files.
- **Phase 3a** — yt-dlp killer features. New SQLite history DB at `%LOCALAPPDATA%\WhisperProject\history.db` with `downloads` and `transcriptions` tables, `mark_interrupted()` on startup, and a `Statistics` menu item showing download/transcription counts, total minutes, and top languages. SponsorBlock category checkboxes in the Advanced dialog (`sponsorblock_categories` config key) — when set, the categories are appended to yt-dlp via `--sponsorblock-remove`. Auto-transcribe-after-download wiring is fully active: a finished media download with `auto_transcribe_after_download=True` enqueues a `TranscriptionTask` with the captured language hint. The `--progress-template "%(progress)j"` JSON parser landed in Phase 1b is now the live progress source for download rows. Right-click history actions on both queue tabs: `Open output folder`, `Re-run`, `Remove`. 17 new unit tests (history 11, auto-transcribe wiring 6).
- **Phase 2a** — Whisper masterpiece. VAD on by default, configurable via three knobs (`vad_min_silence_ms`, `vad_threshold`, `vad_speech_pad_ms`). Word-level timestamps as an opt-in (`word_timestamps`). Language detection captured from `info.language`/`info.language_probability`, posted via a new `language_detected` worker event, and rendered in a new `language` column on the Transcription Queue tab. New `core/writers/` package — six pure writers (`srt`, `vtt`, `tsv`, `txt`, `json`, `lrc`) + a `get_writer` registry. Output formats are user-selectable from a new `Advanced...` dialog (defaults: `["srt", "json"]`). VTT emits karaoke-style `<HH:MM:SS.ms><c>word</c>` cues when words are present. `BatchedInferencePipeline` wraps the model on CUDA when available. `initial_prompt` and `hotwords` plumbing in place (UI in Phase 2b). 39 new unit tests + 4 real-audio smoke tests + 3 end-to-end tests.
- **Phase 1b** — Foundation refactor. The 1296-line `gui.py` becomes an 11-line `--worker`-aware entry point; the rest is now an `app/` package with `app.py` (Tk root, ~430 lines), `dialogs/`, `domain/`, `services/` (DownloadService, FormatService, TranscriptionService, IntegrationsService), `widgets/` (console + tab builders), and `observability.py` (env-gated Sentry). Per-instance queues replace module globals (closes AUDIT B3). `pyproject.toml` lands at the repo root with `[project.optional-dependencies]` for `dev`, `crash_reporting`, `theme_detection`. (PHASE_NEXT_BRIEF Phase 1b)
- **Phase 1b / tests** — `tests/core/` adds 71 new unit tests (config 9, model_manager 10, worker_protocol 10, subtitle_lang_args 10, download_command 20, transcriber_helpers 12). `core/` line coverage rises to 77% overall; testable modules sit at 81–92%.
- **Phase 1b / type hints** — `from __future__ import annotations` + complete type signatures across every `core/` module. `pyright core/` is clean (0 errors, 0 warnings).
- **Phase 1b / observability** — `app/observability.py` opt-in Sentry hook. Activated only when `SENTRY_DSN` env var is set. No DSN ever in code, config, or git history.
- **Phase 1b / acceptance** — `docs/PHASE_1B_ACCEPTANCE.md` with grep-able tests 1B-T1 through 1B-T7.
- `README.md` at project root — first-class entry point for new readers
- `docs/ARCHITECTURE.md` — describes the current process model, layout, key flows, and design rationale
- `docs/AUDIT.md` — full audit findings tagged critical / high / medium / low
- `docs/ROADMAP.md` — six-phase plan based on competitive analysis of nine Whisper GUI projects and eight yt-dlp GUI projects
- `docs/CHANGELOG.md` — this file
- `docs/CONFIG.md` — `config.json` field reference
- `docs/DECISIONS.md` — short ADRs for the load-bearing architectural choices
- `docs/PHASE_1_ACCEPTANCE.md` — machine-parseable test plan for Phase 1a (theme + platformdirs + logging)
- `.gitignore` — first proper gitignore for the project
- `requirements.txt` — runtime dependencies, with Phase 1/2 additions commented for later
- `Phase 0 fixes` — see "Changed" and "Fixed" below
- **Phase 1.1** — Sun Valley theme via `sv-ttk`. Selectable Light / Dark / System under `View` menu, persisted via the new `theme` config key. Transcribe tab `tk.Label`/`tk.Button`/`tk.Entry` widgets converted to `ttk` equivalents so the theme applies uniformly. (ROADMAP 1.1)
- **Phase 1.2** — `platformdirs`-backed config, cache, and log directories. `core/config.py` now exposes `user_config_dir()`, `user_cache_dir()`, `user_log_dir()`, `user_data_dir()`. New `migrate_config_location()` runs on every `load_config()` call: a legacy `config.json` next to source is copied to `%LOCALAPPDATA%\WhisperProject\config.json` and the original renamed to `.migrated.bak`. `model_path` defaults derived from `user_cache_dir()`. (ROADMAP 1.2)
- **Phase 1.3** — `core/logging_setup.py` with `setup_logging()`, `get_ui_logger()`, and `open_log_folder()`. `RotatingFileHandler` writes to `<user_log_dir>/app.log` (5 MB × 3). Both `gui.py` and `core/worker.py` call `setup_logging` at startup. Every previous `print()` outside the worker's JSON `emit()` is now a `logging.getLogger(__name__).info/warning/error` call. New `Help → Open log folder` menu item. (ROADMAP 1.3)
- **Phase 1.5** — `sv-ttk>=2.6.0` and `platformdirs>=4.0.0` promoted from "Phase 1 additions (uncomment when implementing)" to active dependencies. (ROADMAP 1.5)
- `docs/integrations/` — new home for cross-tool integration notes. Contains a `README.md` index, a research note + implementation brief for **oTranscribe** (web-based manual transcription tool). The pattern is: every integration gets a research note authored before code, a hands-off brief that drives an autonomous session, and an acceptance plan added when the work lands. Documents survive the merge — never deleted.
- `docs/integrations/otranscribe-research.md` — full schema of the `.otr` file format (plain JSON with four keys: `text` HTML, `media`, `media-source`, `media-time`), the timestamp `<span>` HTML structure, oTranscribe's import/export limitations (imports only `.otr`; exports `.otr`/`.txt`/`.md` with no SRT/VTT), keyboard shortcuts, and a three-tier integration plan (MVP converters / UI buttons / power features).
- `docs/integrations/otranscribe-brief.md` — implementation brief modeled on `docs/PHASE_1_BRIEF.md`. Three public functions (`srt_to_otr`, `whisper_json_to_otr`, `otr_to_srt`), three UI additions (Export menu item, Import button, Help → Open oTranscribe), pytest fixtures, nine grep-able acceptance tests, hands-off push policy, and the eight known traps that survived Phase 1's discovery (newlines inside `text`, NBSP after the timestamp span, no zero-padding on the hour, etc.).
- **Phase 2-oTranscribe** — bidirectional `.otr` file-format converter at `core/integrations/otranscribe.py`. Public surface: `fmt_otr_time`, `srt_to_otr`, `whisper_json_to_otr`, `otr_to_srt`. Stdlib only (`json`, `html`, `html.parser`, `re`, `pathlib`); zero new runtime deps.
- **Phase 2-oTranscribe / UI** — `Transcription Queue` right-click on a `finished` task gains `Export → oTranscribe (.otr)` (writes `<base>.otr` next to the existing `<base>.srt`). `Transcribe` tab gains an `Import .otr → SRT...` button that runs through two file pickers. `Help → Open oTranscribe...` opens the official site in the user's browser.
- **Phase 2-oTranscribe / tests** — `tests/integrations/test_otranscribe.py` with nine pytest cases (display format, ASCII round-trip, Persian round-trip, whisper-JSON conversion, NBSP boundary, single-line `text`, last-segment end inference, `media` basename only, smoke). Fixtures under `tests/integrations/fixtures/`.
- `docs/integrations/otranscribe-acceptance.md` — machine-parseable acceptance plan for the oTranscribe integration with a mandatory final JSON block.

### Fixed

- **CRITICAL**: `yt-dlp --update` no longer blocks every download. The unconditional pre-download update call previously broke offline use and any case where GitHub was rate-limiting. Update is now gated to once per launch (and only when the user opts in via `auto_update_yt_dlp` setting). Failures log and continue. (AUDIT A1)
- **CRITICAL**: `core/transcriber.py`'s `detect_device` no longer swallows `KeyboardInterrupt` and `SystemExit` via a bare `except:` (AUDIT A2)
- **CRITICAL**: `get_duration` in `core/transcriber.py` now resolves `ffprobe` from the bundled `bin/` folder instead of expecting it on `PATH` (AUDIT A3)
- **HIGH**: `current_video_language` is now only captured when the lookup result still matches the current URL — fixes wrong-language hint after rapid URL changes (AUDIT A4)
- **HIGH**: Partial subtitle files are deleted when the subtitle phase is cancelled mid-write (AUDIT A5)
- **HIGH**: `config.json` is written atomically (`.tmp` + `os.replace`) so a crash during save can no longer leave the file corrupt (AUDIT C1)
- **HIGH**: `load_config` falls back to baked-in defaults if `config.json` is missing or invalid, instead of crashing at startup (AUDIT C2)
- **CRITICAL**: `load_config` now repairs unreachable `model_path` (e.g. config referencing an unmounted drive like `X:\`) by substituting `%LOCALAPPDATA%\WhisperProject\models\<model-folder>`. Unreachable `download_folder` is cleared so the UI re-prompts. This fixes the `[WinError 3] The system cannot find the path specified: 'X:\\'` crash during model setup. (AUDIT C7, escalated from LOW after a real user hit it.)

### Changed

- `transcriber.py`'s busy-wait loop in `transcribe()` replaced with an `assert MODEL_READY` since the only call path goes through `load_existing_model` first (AUDIT B6)

---

## [0.3.0] — 2026-05-11

### Added

- Automatic subtitle download in the "Download Videos" tab — checkbox plus 30-language combo (`docs/auto-subtitles-feature.md`)
- Per-phase status indicator next to the subtitle combo
- `download_subtitles_enabled` and `download_subtitle_lang` persisted to `config.json`
- Subtitle phase explicit `--- Subtitle phase: … ---` markers in the console log
- `--write-auto-subs` AND `--write-subs` in one yt-dlp call — yt-dlp prefers manual captions when available

### Changed

- `SUBTITLE_LANGUAGES` reordered to Automatic, English, then alphabetical (was: arbitrary regional grouping)
- Multi-variant language entries collapse `zh-Hans,zh-CN`, `no,nb`, `he,iw`, `id,in`, `pt,pt-BR,pt-PT`, `es,es-419`
- Subtitle combo starts in `state="disabled"` to avoid a readonly→disabled flash on launch

### Fixed

- `--sub-langs en.*` was matching translated captions like `en-de-DE`, `en-ja`, `en-pt-BR`, downloading 7 files instead of 1. Now uses exact codes joined with commas.
- "no subtitles" detection regex now matches yt-dlp's actual output (`There are no subtitles for the requested languages` / `no automatic captions for the requested languages`) instead of the never-triggered `WARNING: There are no` pattern

---

## [0.2.0] — 2026-05-07

### Added

- Bundled `yt-dlp.exe` in `bin/` for video downloads
- "Download Videos" tab with URL input, format detection via `yt-dlp --dump-single-json`, audio-only and audio+video modes, output format selection
- Download queue with progress, cancel, remove

---

## [0.1.0] — Initial version

### Added

- Tk GUI for `faster-whisper` transcription
- Worker subprocess model with JSON event protocol
- Resumable, MD5-verified model download from a CDN mirror
- Transcription queue with cancel, pause/resume, retry
- Multiple parallel workers (`parallel_workers` config)
- SRT and JSON output next to the input file
