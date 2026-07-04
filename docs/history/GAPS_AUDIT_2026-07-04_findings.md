# GAPS_AGAINST_PEERS_2026.md audit findings — 2026-07-04

Raw findings from two independent subagent passes, saved verbatim so
they aren't lost before being applied to `docs/GAPS_AGAINST_PEERS_2026.md`.
Batch 1 (10 rows) is already applied and pushed — see that file's own
history. Nothing below has been applied yet.

---

## Agent A — sections A (Core ASR), B (Editor/viewer), D (Workflow/ingestion)

Spot-check performed: `python gui.py --help` confirmed the `transcribe`/`serve` CLI subcommands claim directly.

### Section A — Core ASR features

| Row | Current claim | Verdict | Evidence | Suggested correction |
|---|---|---|---|---|
| Word-level ±50ms alignment | Whisper-native timestamps (drift up to ±500ms) | Stale | `core/alignment.py` (stable-ts DTW refinement to ±50ms, opt-in); `tests/core/test_alignment.py`; UI: `app/dialogs/advanced.py:395-405` "Word alignment" combobox (`none`/`stable_ts`), saved to `cfg["alignment"]` (line 958) | shipped (opt-in, off by default) |
| Live mic transcription | absent | Stale, but genuinely partial | `core/recorder.py` — mic via `sounddevice`, system-loopback via `pyaudiowpatch`; own docstring: "live-streaming transcription itself is a Phase 2 RealtimeSTT integration if/when that lands" | partial — a "Live" tab records mic/system-audio to WAV then feeds the normal transcribe pipeline (record-then-transcribe). True continuous streaming not built |
| System-wide dictation hotkey | absent | Confirmed still accurate | No hotkey/keyboard-hook code anywhere; absent from the app's own About-dialog feature list | no change |
| Multiple Whisper sizes in UI | hard-coded large-v3 | Stale | `core/model_manager.py` `MODEL_REGISTRY` has tiny/base/small/medium/large/distil/turbo variants; `app/dialogs/advanced.py:338-367` full combobox with download-status labels, "?" info button, "Download now" button | shipped — full model picker |
| GPU vs CPU choice in UI | auto-detected, not surfaced | Stale | `app/widgets/hardware_wizard.py` `HardwareWizard` Toplevel, override + persistence to `hardware.json` + benchmark button; wired from `advanced.py:419` → `_open_hardware_wizard` (1070) → `HardwareWizard(...)` (1085) | shipped — Hardware wizard with override + persistence + benchmark |
| Alternative backends | absent — faster-whisper only | Stale | `core/backends/{base,faster_whisper_be,whisper_cpp,cloud_stt,google_cloud_stt,nvidia_asr}.py`; `core/backends/availability.py:22-37` `ENGINE_CHOICES` = 5 engines; `app/widgets/tabs.py:296-313` engine combobox | shipped — 5 backends behind a common `Backend` ABC |
| Custom hot-words UI | config only, no UI | Stale, but not the full "glossary editor" | `app/dialogs/advanced.py:124,377-380,924` "Hotwords (comma-separated)" Entry wired to `cfg["hotwords"]` | upgrade from "no UI" — single global text field, not a per-project glossary manager |
| Language picker per-file | set in config, not per-task | Stale | `app/widgets/tabs.py:243-245,330-340` "Language:" combobox on the Transcribe tab, deliberately not restored from config, applied per task via `_apply_task_options` | shipped |
| Translation (task=translate) | absent | Confirmed still accurate (as a user feature) | No real `task="translate"` usage; `core/llm.py:298-307` has an unused LLM-based `translate()` helper with zero call sites in `app/` | no change, footnote the unused helper |
| Voice/track separation | absent | Stale | `core/separator.py` Demucs htdemucs pre-process with disk cache; `core/config.py:219-226` `demucs_enabled` (default False); `advanced.py:185-186,454-455,960` checkbox | shipped (opt-in, off by default) |
| PII / entity redaction | absent | Confirmed still accurate | No redact/PII/entity feature anywhere | no change |
| Sound-event tags | absent | Confirmed still accurate | No [Music]/[Applause]/AED code anywhere | no change |
| Auto-resume after crash | marks interrupted, doesn't re-queue | Stale | `core/history.py` `mark_interrupted()`/`dismiss_interrupted_transcriptions()`; `app/app.py:679-681,4203-4308` "Resume interrupted transcriptions?" dialog, re-enqueues on accept; `tests/core/test_crash_resume*.py` | shipped — exactly the "prompt at startup" the row asked for |

### Section B — Editor / playback / transcript viewing (all 10 rows via `app/dialogs/transcript_viewer.py`, 1524 lines)

Wired in via `app/app.py`: Last-Result card button (348, 3809-3818), File menu (863, 1011-1039), queue right-click (2362-2363). README already documented this.

| Row | Verdict | Evidence | Correction |
|---|---|---|---|
| In-app transcript viewer | Stale | `TranscriptViewer` class, segment Treeview + VLC panel; `tests/core/test_transcript_viewer.py` | shipped |
| Click-word → seek | Stale, segment not word granularity | `_on_segment_select` → `_seek_to`; `_words_lbl` is a non-interactive Label | shipped as click-to-seek on a **segment**, not literal per-word click |
| Inline transcript editing | Stale, genuinely partial | `FindReplaceDialog` + `_remove_fillers` + `_rename_speaker`; `_save_changes` (854-882) writes only back to source `.json`, no re-export to SRT/VTT/TXT, no free-text cell edit | partial |
| Karaoke-style word highlight | Stale | `_update_karaoke` — bisect_right over segment starts, 250ms VLC-position poll | shipped |
| Search inside transcripts | Stale, half the claim | In-viewer search (`search_var`/`_refilter`) shipped; `core/search.py` FTS5+semantic cross-history search fully built and tested but imported by **no file under `app/`** | partial — open-transcript search shipped, cross-history engine has zero UI entry point |
| Speaker rename (global) | Stale | `_rename_speaker` — right-click → rename everywhere **within the open transcript** | shipped, "everywhere" = current transcript only |
| Filler-word remove | Stale | `_FILLER_WORDS`, `_filler_regex()`, `_strip_fillers()`, confirm dialog | shipped |
| Find-and-replace | Stale | `FindReplaceDialog` — find-next/replace/replace-all, case toggle, backreference-safe | shipped |
| Embed media player | Stale | `_try_load_vlc`/`_init_vlc_player`/`_bind_vlc_window`; graceful fallback to system player | shipped via python-vlc with real fallback |
| Word-confidence colour coding | Stale | `_segment_min_probability()` + tag_configure at 0.85/0.6 thresholds | shipped |

### Section D — Workflow / ingestion

| Row | Verdict | Evidence | Correction |
|---|---|---|---|
| Drag-and-drop | Stale | `app.py:704,4451-4492` tkinterdnd2, graceful no-op if missing; `_split_dnd_paths`; `tests/core/test_dnd_paths.py` | shipped (optional dep) |
| Batch queue multi-select | Stale | `app.py:1739-1755` `browse()` uses `askopenfilenames` (plural), enqueues each | shipped |
| Watched folders | Stale | `core/watcher.py` `FolderWatcher` (watchdog, lazy-import); config `watched_folder`/`watched_folder_enabled`; `app.py:741,3896-3915` | shipped (optional dep) |
| YouTube URL on Transcribe tab | Stale | `app.py:2053-2070` `add()` detects URL, auto-fills Download field, flips auto-transcribe, switches tab | shipped |
| Right-click Explorer integration | Stale | `installer_embed.iss:50,57-63` / `installer.iss` — `HKCR\*\shell\WhisperProjectTranscribe`, default-on Inno task `shellext` | shipped as optional (default-on) install task |
| CLI mode | Stale | `gui.py:156-213` `_build_argparser()` — real `transcribe`/`serve` subcommands; confirmed live via `python gui.py --help` | shipped |
| Per-project / per-folder settings | Stale | `core/config.py:1019-1154` `.whisperproject.json`, `load_project_overrides()`; actually called from `core/transcriber.py:1149-1156,1205-1214` and `core/server/jobs.py` | shipped — real, wired into both desktop and HTTP paths |

---

## Agent B — sections E (UI), F (Distribution), H (Performance), I (SMTV/yt-dlp), C (3 rows)

Cross-verified live via `gh run list` / `gh release view` (not just reading YAML/reading code).

### Section E — UI / presentation

| Row | Verdict | Evidence | Correction |
|---|---|---|---|
| Windows toast notification | Stale | `app.py:3833-3846` fires `tray.notify()` on every completed job; `tray.py:221-231` calls pystray's native toast; installs automatically whenever pystray+Pillow present | shipped — bell **and** native toast |
| High-DPI scaling | Stale | `app.py:603-605,4431-4448` `_apply_hidpi_scaling()`, explicit `winfo_fpixels("1i")`-based scale factor; `tests/core/test_app_hidpi.py` (5 tests) | shipped — explicit computation, tested |
| Resizable/dockable result panel | Stale, nuanced | Last Result card genuinely fixed (`tabs.py:426-433`); but `transcript_viewer.py:372-511` is a separate resizable Toplevel with a real `ttk.PanedWindow` draggable sash | Last Result card fixed by design; the transcript-viewing surface it launches is resizable/paned |
| Window state persistence | Stale | `app.py:606-617` restores `window_geometry`; `app.py:4591-4603` `_save_window_geometry()` called in `on_exit` (line 1438) | shipped |
| Accessibility / screen reader | Confirmed still accurate | No UIA/MSAA/NVDA/JAWS code anywhere | no change |

### Section F — Distribution and trust

| Row | Verdict | Evidence | Correction |
|---|---|---|---|
| Code-signed exe | Confirmed still accurate | No codesign/signtool pipeline; CLAUDE.md keeps it forbidden-unless-asked | no change |
| Notarised macOS build | Stale, significant | 3 real macOS paths (install.command, Homebrew formula, PyInstaller .app→.dmg); `macos-compileall-script-test.yml` run `28691357195` completed/success 2026-07-04, 3m9s; `macos-app.yml` has successful arm64+x86_64 runs; repo confirmed public; real .dmg artifacts already in `dist_installer/`. Still explicitly unsigned/un-notarized. | not notarised, but no longer N/A/Windows-only — 3 working paths exist, one verified end-to-end on real macOS runners. Effort more realistically M (buy a cert) than XL (porting is done) |
| Auto-update from inside the app | Stale, partial | `core/updates.py`/`app.py:883-884,4003-4069` "Check for updates" hits GitHub releases API, compares versions, but only ever notifies (`_on_update_result` only calls `webbrowser.open`) | partial — real notify-only update check exists; auto-download/install still absent |
| Per-machine + per-user install | **Stale — appears simply wrong** (flagged for human spot-check) | `installer.iss:25` and `installer_embed.iss:31` both hardcode `PrivilegesRequired=admin`; zero hits for `PrivilegesRequiredOverridesAllowed`; both use `DefaultDirName={autopf}\...`; `docs/INSTALL.md:42` confirms "Asks for admin rights (Yes)" with no alternative | likely should flip to "absent, not partial" — no per-user install mode exists in either installer; Portable ZIP is a different distribution method, not an installer mode |
| Linux / Flatpak / AppImage | Stale | `platform/linux/{install,update,uninstall}.sh` + README; `.github/workflows/ci.yml:27,54-76` runs the full suite on ubuntu-latest × py3.11/3.12 under xvfb-run; but zero Flatpak/AppImage/.deb packaging found | partial, not Windows-only — Linux is real + CI-tested via source/venv installer, no packaged binary yet |
| Reproducible builds | Confirmed still accurate | No SOURCE_DATE_EPOCH/determinism tooling; build_embed_installer.bat always fresh-downloads | no change |
| Crash reporting | Stale | `app/observability.py:103-117` `init_sentry()`, wired at `app.py:645`, gated on `telemetry_opt_in` AND `$SENTRY_DSN`; `tests/core/test_observability.py` | shipped — gated, silent with no DSN |
| Release-notes RSS/API | Confirmed still accurate (footnote) | No latest.json/appcast; but `core/updates.py` already consumes GitHub's releases/latest API programmatically | no verdict flip, footnote only |

### Section H — Performance / packaging

| Row | Verdict | Evidence | Correction |
|---|---|---|---|
| Onefile size (190.8 MB) | Stale, wrong pipeline | Onefile unshipped, now ~447MB per BUILD.md; actual shipped: Setup-Standard 225,633,411 B (~226MB), Portable.zip 343,163,055 B (~343MB) — both cross-verified local disk vs `gh release view v1.5.0` | describe the actually-shipped artifacts instead |
| Cold start (~6s onefile, ~3s onedir/embed) | Stale framing / uncertain number | Onefile unshipped; embed launches via `pythonw.exe gui.py` (no PyInstaller bootloader at all) — architecturally different from whatever number this was; no fresh measurement found | **uncertain, needs human spot-check** — someone should actually time the current shipped launch path |
| Memory footprint (~2GB) | Confirmed still accurate | Default backend unchanged; footnote: `whisper_cpp.py`'s q5_0 model (~1.1GB) already gives a lower-memory alternative | no change, optional footnote |
| GPU acceleration tested per release | Confirmed still accurate | ci.yml matrix is windows/ubuntu only; zero cuda/gpu/nvidia hits across all 9 workflow files | no change |
| Streaming download w/ resume+checksum | Confirmed still accurate | `core/model_manager.py` MD5 checksums; `tests/core/test_model_manager.py` | no change |
| Quantised model support | Stale | `core/backends/whisper_cpp.py` runs ggml q5_0 (~1.1GB) via pywhispercpp; wired into Advanced dialog backend picker with one-click download; 7+ tests | shipped — q5_0 selectable; only q5_0 wired (no q4_K_M), so a smaller residual gap remains |

### Section I — SMTV / yt-dlp / integration

All 5 rows: **confirmed still accurate**, no change (yt-dlp passthrough, SMTV scraper, other niche scrapers absent, YouTube subtitle download, live URL/RTMP/HLS ingestion absent — `core/recorder.py` and `core/tiling.py` explicitly don't close this since tiling is display-only).

### Section C — 3 specified rows

| Row | Verdict | Evidence | Correction |
|---|---|---|---|
| Per-format batch export from one transcript | Stale, partial | `core/convert.py` + `app.convert_transcript`/`_ask_convert_format` re-export any transcript to any other single format post-hoc, no ASR re-run; 16 tests. Picker is single-select combobox, not true one-click multi-format batch | partial — post-hoc single-format re-export shipped; literal one-click multi-format batch still absent |
| Output filename templating | Stale, flatly wrong now | `core/config.py:120` `output_filename_template` default `"{base}.{ext}"`; `core/transcriber.py:613-691` `_render_filename_template` supports `{base}/{ext}/{lang}/{date}/{speaker_count}` + malformed-template fallback + path-traversal guard; 9+ tests. Not documented in docs/CONFIG.md (a docs gap, not a code gap) | shipped — fully tokenized, tested |
| Output directory templating | Stale, partial | Same mechanism supports a sibling subfolder (e.g. `"transcripts/{base}.{ext}"`, auto-created), tested; but path-traversal guard rejects any path outside the source file's own directory tree | partial — per-source sibling subfolder shipped; one common folder across different source directories still impossible |

---

## Not yet done (next session)

1. ~~Spot-check the 2 flagged-uncertain items~~ — **DONE 2026-07-04 (later session):**
   - Per-machine/per-user install (F): confirmed the reversal is correct — both
     `installer.iss` and `installer_embed.iss` hardcode `PrivilegesRequired=admin`
     with no `PrivilegesRequiredOverridesAllowed`; flipped row F to 🔴 absent
     in `docs/GAPS_AGAINST_PEERS_2026.md`.
   - Cold start (H): directly measured against the real shipped launch path
     (`embed_build/python/pythonw.exe gui.py`, timed via a PowerShell stopwatch
     polling for `MainWindowHandle`) — **~4.7 s on a fresh disk cache, ~1.9 s
     warm** (two repeat runs). Updated row H with the real numbers and dropped
     the stale "onefile"/"onedir" framing (the shipped path is neither — it's
     the embed tree with no PyInstaller bootloader).
2. Apply the REMAINING confirmed corrections above (rows other than F/H) to
   `docs/GAPS_AGAINST_PEERS_2026.md` — still open.
3. Rewrite Section J's "top 5 gaps" verdict — given how much shipped, the real remaining big gap is mostly the system-wide dictation hotkey; DOCX/MD, CI, diarization, and the in-app viewer are all done now.
4. Fix the "164 tests" mention in Section J (actual: 1701 collected this session, full suite green, exit code 0).
5. Grep for any other stale test-count mentions in the file.
6. Commit and push.
