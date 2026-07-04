# Audit & Findings

A complete review of the current codebase by an external architect, plus a benchmark against mature open-source competitors. Findings are tagged by severity:

- **CRITICAL** — bug, security issue, or data-loss risk. Fix before next release.
- **HIGH** — meaningful correctness or UX problem. Fix in the next iteration.
- **MEDIUM** — code-quality or maintainability issue. Fix during normal refactor.
- **LOW** — polish, nice-to-have.

The findings here are the basis for `ROADMAP.md`. This file says *what's wrong*; the roadmap says *what to do next*.

---

## A. Critical bugs

### A1. CRITICAL — `yt-dlp --update` blocks every download

`gui.py:964-971` runs `yt-dlp --update` synchronously before every single download and raises on non-zero return code. This means:

1. Every download pays a network round-trip to GitHub before starting.
2. If GitHub is rate-limited, behind a firewall, or down, **no download can start** — the worker throws `RuntimeError("yt-dlp update failed")`.
3. The update writes to `bin/yt-dlp.exe`, which can race with a concurrent download in progress (we serialize downloads, so today it's safe, but future-fragile).

**Fix:** move update behind a setting, run it at most once per launch (or once per day via a timestamp in `config.json`), and never fail the user's download because of an update problem. Log the failure and continue.

### A2. CRITICAL — bare `except:` swallows `KeyboardInterrupt` and `SystemExit`

`core/transcriber.py:25`:

```python
try:
    import torch
    if config["device"]=="auto" and torch.cuda.is_available():
        return "cuda","float16"
except:
    pass
```

The bare `except` catches `KeyboardInterrupt`, `SystemExit`, `BaseException`. Ctrl+C during this call disappears. **Fix:** narrow to `except Exception:` or, better, `except (ImportError, AttributeError):` because torch is the only thing that can plausibly fail here.

### A3. CRITICAL — `get_duration` calls `ffprobe` from PATH, not the bundled binary

`core/transcriber.py:95`:

```python
r=subprocess.run(["ffprobe","-v","error",...],...)
```

The whole point of shipping `bin/ffprobe.exe` is that the user doesn't need it on `PATH`. This call hard-fails on a clean machine because `ffprobe` is not found. **Fix:** resolve to `bin/ffprobe.exe` (relative to the project root) the same way `yt_dlp_path()` does.

### A4. HIGH — Race on `current_video_language`

`gui.py:226` `self.current_video_language` is set inside `poll_format_events` (Tk main thread) and read inside `add_download` (also Tk main thread, so no actual race today). But the value reflects whichever URL was last looked up. If the user pastes URL A, the lookup starts, they paste URL B, B's lookup wins, then they hit Download before B finishes — the captured `detected_language` belongs to A's lookup that came back later.

The mitigation in `poll_format_events:644-645` (`if url != self.download_url_var.get().strip(): continue`) only protects the combos, not `current_video_language` because the assignment happens after the URL check. **Fix:** also gate the `current_video_language` assignment on URL-match, or capture the URL at the time the task is created and look up its language on demand.

### A5. HIGH — Subtitle phase can leave a partial `.vtt` file on cancel

`docs/auto-subtitles-feature.md` admits this in "Known limitations." A cancelled subtitle phase that was mid-write leaves a truncated `.vtt`. **Fix:** track which file yt-dlp was last writing (`Writing video subtitles to:` lines we already parse into `wrote_files`) and, on cancel, delete entries that are now smaller than the manifest expected. Simpler: on cancel, delete every file listed in `wrote_files` since yt-dlp may have only partly flushed.

### A6. HIGH — `restart_worker` can mis-route events from the dead worker

`gui.py:339-345`:

```python
def restart_worker(self, worker):
    self.stop_worker(worker)
    worker["process"]=None
    ...
```

The stdout reader thread for the old subprocess is still alive at this point. It will keep pushing events with the old `_pid` until stdout closes. The new process gets the same `worker["id"]` and a different `_pid`, so `worker_for_event` will drop old events correctly — but if `worker_exit` for the old PID arrives **after** the new process emits `ready`, the old `worker_exit` will not match because `process.pid != event._pid`. That works. But the call to `restart_worker` from the cancel path (`gui.py:843`) does not wait for the old reader to drain. A handful of stale events sit in `worker_events` briefly, get matched by `worker_id` and a `pid` we've already replaced, and are silently dropped by `worker_for_event` returning `None`. Not a bug today, but the silent-drop policy hides issues. **Fix:** log dropped events at debug level, or better, give workers a generational `instance_id` that survives across restarts and route on that.

### A7. HIGH — `MODEL_ERROR` is sticky across `load_existing_model` calls in the worker

`core/transcriber.py:38-40` does reset `MODEL_ERROR=None` at the start of `load_existing_model`, so this is actually handled. **Downgrade to LOW**: the global-state idiom is fragile and would burn the next person, but it's correct today.

### A8. HIGH — `model_ready=True` race when no workers exist

`gui.py:251-257`:

```python
def update_model_state(self):
    ready_count=len(self.ready_workers())
    self.worker_ready=ready_count > 0
    self.model_ready=self.worker_ready
    self.model_loading=not self.worker_ready
```

After `stop_workers` and `self.workers=[]` (e.g. inside `ensure_model_with_modal` on `startup_error`), `ready_count=0` so `model_loading=True` immediately. But the next code path is `ensure_model_with_modal` which may decide the dialog cannot run (`model_setup_running` already true) and return without starting a worker. The UI is left in `model_loading=True` permanently. **Fix:** track an explicit "no workers" state vs "loading workers" state.

---

## B. Code quality & maintainability

### B1. HIGH — 1156-line `gui.py` does too many jobs

The single file contains: the Tk app, two task classes, a modal download dialog, the worker management protocol, the format-lookup logic, the subtitle phase, the media download phase, the queue tables, the menus, and the console widget. Bus factor of 1, painful to test, painful to navigate.

**Recommended split (incremental):**

```
app/
├── app.py            ← App class, Tk root, wires the rest together
├── tabs/
│   ├── transcribe.py
│   ├── queue.py
│   └── download.py
├── widgets/
│   ├── model_dialog.py        (ModelDownloadDialog)
│   ├── console.py             (the black/lime text widget)
│   └── format_panel.py
├── services/
│   ├── download_service.py    (build_download_command, process_download_queue)
│   ├── transcription_service.py (start_worker, finish_worker_task, poll_worker_events)
│   └── format_service.py      (lookup_formats, poll_format_events)
└── domain/
    ├── tasks.py               (TranscriptionTask, VideoDownloadTask)
    └── subtitle_languages.py  (SUBTITLE_LANGUAGES table)
```

Don't do it all at once. Pull out `ModelDownloadDialog` first (it's already self-contained), then `SUBTITLE_LANGUAGES`, then the format/download services. Each split is one PR.

### B2. HIGH — No type hints anywhere

Adding `from __future__ import annotations` + `mypy --strict` to a 1100-line app catches a class of bugs the eye misses. With `tkinter.ttk` having type stubs in modern Python, the cost is modest. **Recommended:** add `mypy.ini` with a relaxed config, target `core/` first, expand to `gui.py` after the split (B1).

### B3. HIGH — Module-global state (`queue`, `download_queue`, `download_current`)

`gui.py:10-12` declares module-level mutable lists. The `App` instance reaches for them via `global`. This blocks reuse (you can't run two `App`s in one process) and makes testing harder. **Fix:** move all three to `self.transcription_queue`, `self.download_queue`, `self.download_current`. Mechanical refactor.

### B4. MEDIUM — `tk.*` and `ttk.*` widgets mixed inconsistently

The Transcribe tab (`gui.py:461-465`) uses raw `tk.Label`, `tk.Button`, `tk.Entry`. The Download tab uses `ttk.*`. Visual inconsistency on Windows because `tk.Button` is the old Motif-style widget, while `ttk.Button` follows the system theme. **Fix:** convert Transcribe tab to `ttk` to match. Trivial.

### B5. MEDIUM — `transcriber.py` uses module globals for `MODEL`, `MODEL_READY`, `MODEL_ERROR`

Inside a worker subprocess this works (one model per process), but it's brittle. A `WhisperModelHandle` class with `is_ready()`, `transcribe()`, `release()` would be clearer and would make in-process testing possible without the subprocess layer. **Fix:** wrap in a class. Re-evaluate after B1 is done.

### B6. MEDIUM — `transcribe` busy-wait loop is dead code

`core/transcriber.py:104-107`:

```python
while not MODEL_READY:
    if MODEL_ERROR:
        raise RuntimeError(MODEL_ERROR)
    time.sleep(0.5)
```

In the actual call site (`core/worker.py`), `load_existing_model` is called first and only on success does the loop accept `transcribe` commands. So `MODEL_READY` is always True when `transcribe` runs. This loop has no real path that enters it. **Fix:** delete it, or replace with `assert MODEL_READY, "transcribe called before model load"`.

### B7. MEDIUM — `print()` instead of `logging` everywhere

The worker emits JSON on stdout, but `transcriber.py:18` also does `print(msg)` for the no-callback case. Mixing JSON and free-form prints on the same stdout is a recipe for "Invalid worker command" errors. Even though `log_cb` is always passed in practice, the fallback is a footgun. **Fix:** convert all `print` to `logging.getLogger(__name__).info(...)` and configure the worker's logging to stderr (parent already captures stderr). The protocol channel becomes stdout-only-JSON.

### B8. MEDIUM — No `__main__.py`, must run `python gui.py` from inside the directory

`core/config.py:4` derives `config_path()` from `__file__` walking up one level. That works when run as `python gui.py` from project root. It does **not** work if installed as a wheel or run from another cwd. **Fix:** introduce a `__main__.py` at the package root and a `platformdirs`-based config location with a fallback to the next-to-executable layout for portable mode.

### B9. LOW — Comma-separated function arguments without spaces

Pervasive in `gui.py`: `import json,re,subprocess,sys,threading,time,os`. PEP-8 says spaces. **Fix:** `black` or `ruff format` once. One commit, zero behavior change.

### B10. LOW — Magic numbers everywhere

`after(100, ...)`, `after(200, ...)`, `after(300, ...)`, `after(500, ...)` for various poll intervals. `width=80`, `width=24`, padding `(8,0)` repeated. **Fix:** module-level constants (`POLL_INTERVAL_MS = 100`, etc.) so all timing knobs are tunable in one place.

---

## C. Security & robustness

### C1. HIGH — `config.json` write is not atomic

`core/config.py:11-13`:

```python
def save_config(config):
    with open(config_path(),"w") as f:
        json.dump(config,f,indent=2)
        f.write("\n")
```

If the process crashes mid-write, `config.json` becomes empty or truncated, and the next launch fails on `load_config`. **Fix:** write to `config.json.tmp`, then `os.replace(tmp, target)`. Atomic on Windows for same-filesystem renames.

### C2. HIGH — `load_config` has no fallback if file missing or corrupt

`core/config.py:7-9` will raise on file-not-found or invalid JSON, and the GUI crashes at startup before any error message is shown. **Fix:** catch, log, fall back to a baked-in default dict, and show a friendly dialog at first paint.

### C3. MEDIUM — Filenames are user-controlled via `%(title)s`

`gui.py:907` and `gui.py:923` use `%(title)s.%(ext)s` as the output template. `yt-dlp` sanitizes by default, but the user could supply a custom output template if we expose one later. **Future-proofing:** when we add the template UI (see roadmap), ensure we don't pass through path traversal characters or absolute path injections.

### C4. MEDIUM — Subprocess inherit on Windows console

`gui.py:289-291` uses `CREATE_NO_WINDOW` for workers. Good. But `gui.py:1029` uses the same flag inline. Centralize this in a helper to ensure consistency and to add `STARTUPINFO` with `STARTF_USESHOWWINDOW | SW_HIDE` as a belt-and-suspenders defense against any future ffmpeg subprocess we spawn.

### C5. MEDIUM — No checksum verification of `bin/yt-dlp.exe`, `ffmpeg.exe`, `ffprobe.exe`

The model is MD5-verified, but the bundled binaries (which yt-dlp's `--update` will overwrite!) are not. A malicious update server could substitute a binary. **Fix:** record SHA256 of bundled binaries at packaging time and verify on launch. Refuse to launch if hashes don't match (with an override flag for developers).

### C6. MEDIUM — Disk-full / permission errors during download are surfaced as generic errors

If `task.folder` is unwritable, yt-dlp exits non-zero and we log a generic line. **Fix:** precheck `os.access(folder, os.W_OK)` and a small write-probe before spawning yt-dlp. Surface a specific message.

### C7. LOW — `model_path` in `config.json` is absolute and user-specific

`X:\\whisper_cache2\\hub\\models--Systran--faster-whisper-large-v3`. This will not work on any other machine. **Fix:** default to `platformdirs.user_cache_dir("whisper-project")`, allow override.

---

## D. UX, polish & missing features

### D1. HIGH — No language displayed after model auto-detects it

faster-whisper's `transcribe()` returns `info.language` and `info.language_probability`. The current `transcriber.py:113` ignores the info object. **Fix:** capture it and emit a `language_detected` event so the UI can show "Detected: Persian (97%)".

### D2. HIGH — No VAD (Voice Activity Detection)

`MODEL.transcribe()` is called with all defaults. Adding `vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500)` is a one-line change that eliminates the most common Whisper failure mode (hallucinations on silence and music). Should be on by default. **Fix:** add to transcribe call; expose as a checkbox.

### D3. HIGH — No word-level timestamps, no VTT output

Current output is SRT + JSON only. Word-level timestamps are a one-flag change (`word_timestamps=True`) and enable karaoke-style VTT, LRC, and better subtitle splits. **Fix:** see ROADMAP item "Multi-format output."

### D4. HIGH — No batched inference on GPU

faster-whisper's `BatchedInferencePipeline` gives 3-12x speedup on GPU for long files. We're leaving most of the performance on the table. **Fix:** check device == cuda, wrap MODEL in `BatchedInferencePipeline`.

### D5. HIGH — Single-track progress only

Transcription progress is per-segment of the audio, not of the file. For a 90-minute video, the progress bar can sit at 0% for the first minute while the model warms up. The 100% jump at the end is also misleading. **Fix:** emit progress based on `seg.end / duration`, which we already compute. Already done in transcriber.py:125 — good, my mistake. **Downgrade to LOW.**

### D6. HIGH — No drag-and-drop

The transcribe tab requires Browse → file picker. `tkinterdnd2` adds DnD support in ~10 LOC. High-leverage UX change.

### D7. HIGH — No batch / folder transcription

User must add files one at a time. Watching a folder for new files (Buzz does this) is a power-user multiplier.

### D8. HIGH — No model picker

`config.json` has one model. Want to switch to `medium`, `small`, `distil-large-v3`? Hand-edit JSON, restart. **Fix:** model picker combo with download-on-demand for each option.

### D9. HIGH — Persian (Farsi) is in the subtitle language list but Whisper writes Persian output directly to the SRT — no UI surface for the bilingual workflow we know the user does (per the BMD skill set, this user produces Persian subtitles regularly). A "Translate to English" toggle (whisper's `task="translate"`) and a "Detected language: fa | Translate target: en" would close the loop.

### D10. MEDIUM — No history / persisted queue

Close the app, queue is gone. Both transcription history and download history are not persisted.

### D11. MEDIUM — No theming

Default Tk look is a strong signal of "amateur tool." A 5-minute migration to `sv-ttk` (Sun Valley theme) gives the app a modern Windows 11 look with no other code changes.

### D12. MEDIUM — Subtitle output format is always SRT

VTT is the web standard. TSV is the research/MAXQDA standard. Plain TXT for the read-only consumer. LRC for music workflows. **Fix:** checkboxes in the transcribe tab for which formats to write.

### D13. MEDIUM — `large-v3` is hardcoded as the only choice

It's 3 GB on disk, ~5 GB in VRAM, overkill for many use cases. Offer at least `medium` and `distil-large-v3` (English-only, 6x faster).

### D14. LOW — No keyboard shortcuts

Ctrl+O for browse, Ctrl+Enter to enqueue, Ctrl+D for download tab, etc.

### D15. LOW — Console is 8 lines, fixed height, black/lime

Looks like a 1995 terminal. **Fix:** resizable, monospace, dark theme that matches the rest. Or hide behind a "Show log" toggle.

### D16. LOW — No SponsorBlock integration

Tartube has `--sponsorblock-mark` and `--sponsorblock-remove`. Single-flag add to the download command.

### D17. LOW — `bin/` is gitignored and so are downloads — but no `.gitignore` file exists

Currently everything works because `bin/` was never `git add`-ed, but a new contributor cloning the repo would `git add .` and commit the 220 MB of binaries. **Fix:** ship a real `.gitignore`.

### D18. LOW — No `requirements.txt` or `pyproject.toml`

Whoever installs has to read the source to discover `requests`, `faster-whisper`, `torch` (maybe). **Fix:** ship `requirements.txt` (or better, a `pyproject.toml` with optional `[gpu]` extras).

### D19. LOW — No `README.md`

The only entry point for a new reader is `gui.py`. **Fix:** README with screenshot, install steps, "what is this," "what isn't this."

---

## E. Comparison with competitors

I surveyed nine projects in the Whisper-GUI space and eight in the yt-dlp-GUI space (see `ROADMAP.md` Appendix for the full table). The gap analysis:

### What our project does **better** than most competitors

- **Bundled binaries (ffmpeg, ffprobe, yt-dlp)**: most Whisper GUIs assume system ffmpeg. We don't.
- **Subprocess worker model with JSON protocol**: cleaner than threads-with-shared-state used by many.
- **Resumable model download with MD5 verification of every extracted file**: most projects skip this and silently use a corrupt model.
- **Subtitle-phase isolation in the yt-dlp pipeline**: the per-phase status indicator and the policy of "never abort media because of subs" is more thoughtful than yt-dlg or Open Video Downloader.

### What competitors do better — by impact

1. **CustomTkinter / sv-ttk theming** (CheshireCC, cbro33) — biggest single visual upgrade.
2. **VAD + diarization + word-level timestamps** (Buzz, WhisperX, Whisper-WebUI, CheshireCC) — biggest single functional upgrade.
3. **Model manager with HuggingFace integration** (CheshireCC, cbro33) — locks in power users.
4. **Folder watcher** (Buzz) — multiplies throughput for the same user.
5. **Integrated text+audio editor** (Buzz, aTrain) — turns the app from a transcriber into a subtitle workshop.
6. **Live microphone mode** (Buzz, Const-me) — opens the meeting-notes use case.
7. **CLI parity** (Buzz, Purfview) — automation users.
8. **REST API / server mode** (Whisper-WebUI) — remote/headless use.
9. **Persistent queue / history** (yt-dlg, Tartube) — sessions survive restarts.
10. **Auto-update for yt-dlp binary** (cbro33, Seal) — should not block downloads, see A1.
11. **Smart progress: `--progress-template "%(progress)j"`** (best practice across modern yt-dlp wrappers) — replaces fragile regex parsing of `[download] N%`.
12. **Preset system (TOML or JSON)** (dsymbol, Stacher) — Supreme Master TV preset = initial_prompt + hotwords + output template + subtitle format in one click.
13. **SponsorBlock flags** (Tartube) — one-line add.
14. **Drag-and-drop + recursive batch** (CheshireCC, Buzz) — already mentioned.
15. **Command preview / editable args** (Stacher) — power-user escape hatch.

### What no competitor does well — our chance to leapfrog

- **Tight yt-dlp ↔ Whisper integration**: download a video → automatically queue its audio for transcription with the right language hint (`detected_language` from yt-dlp metadata becomes the `language` arg in Whisper). Today these are two separate tabs. Combining them as a single "Get subtitles from a URL" mode would be a unique selling point.
- **Bilingual Persian-English workflow** in one tool — Buzz doesn't, CheshireCC doesn't, none of them are aware of the BMD/Supreme Master Television workflow this user lives in. We can build it natively (hotwords + Persian RTL preview + ready-to-paste-into-SubtitleEdit format).
- **MD5-verified, resumable model download** is good differentiation. Most projects use `huggingface_hub` which is great until it isn't. The mirror-on-smch.ir approach plus integrity verification is more robust for users behind unreliable networks.

---

## F. Outright dead code / cleanups

### F1. `core/__init__.py` is empty — fine, but document it

### F2. `gui.py:11` `download_queue=[]` shadowed by `App.download_queue` later? No — `App` never sets `self.download_queue`; it reads the module-global. So removal of module global breaks things. See B3 — needs to be a refactor, not a delete.

### F3. `worker_for_event` returns `None` and the event is silently dropped (B6 covers this). Either log or assert.

### F4. `gui.py:332` `except Exception: pass` swallows shutdown-pipe errors. Acceptable if commented; not commented. **Fix:** add a one-line comment explaining the intent (worker may have already exited).

### F5. `core/task.py` is 9 lines but defines only `TranscriptionTask`. `VideoDownloadTask` is defined in `gui.py:188`. **Fix:** move `VideoDownloadTask` into `core/task.py` alongside `TranscriptionTask`.

---

## G. Testing & CI gaps

The project has **zero tests**. No `tests/` directory, no CI config, no smoke-test script. Specific suggestions:

- `tests/test_model_manager.py` — mock `requests`, test the MD5 parse / mismatch / resume paths. High value because this code is non-trivial and not exercised on every launch.
- `tests/test_subtitle_lang_args.py` — small, pure-function test of the multi-variant logic.
- `tests/test_download_command.py` — test `build_download_command` for each (mode, output, audio_choice, video_choice) combination.
- `tests/test_worker_protocol.py` — spawn `python -m core.worker`, feed a known WAV, assert event sequence.
- A `Makefile`/`tasks.py` for `test`, `lint`, `format`, `run`.
- GitHub Actions: `python -m pytest`, `mypy`, `ruff` on every push. The repo has a remote `master`, so CI is feasible.

---

## H. Documentation gaps

Currently in `docs/`: only `auto-subtitles-feature.md` (excellent, very thorough).

Missing:

- `README.md` (project root) — what is this, install, run, screenshot
- `docs/ARCHITECTURE.md` — now exists (this commit)
- `docs/AUDIT.md` — now exists (this file)
- `docs/ROADMAP.md` — next file in this commit
- `docs/INSTALL.md` — Windows / Linux / macOS install, GPU driver notes
- `docs/CONFIG.md` — every `config.json` field documented with default and effect
- `docs/CONTRIBUTING.md` — code style, how to run tests, how to add a feature
- `docs/CHANGELOG.md` — start now, before history is lost
- `docs/DECISIONS.md` — short ADRs (architecture decision records) for the chunky choices (subprocess workers, yt-dlp binary not library, MD5 over zip, etc.)

---

## Summary

The codebase is **functionally complete** and **better-thought-out than its size suggests** — the subtitle feature audit log is exemplary, the worker protocol is clean, the model download is robust. But it is *one engineer's working draft*, not a product:

- One critical correctness bug (A1, yt-dlp --update),
- Two correctness foot-guns (A2 bare except, A3 ffprobe on PATH),
- A massive monolithic gui.py,
- No tests, no CI, no README, no requirements.txt, no theming, no VAD, no word timestamps, no batched inference, no folder watcher, no model picker, and no drag-and-drop.

The fixes for the critical issues are mechanical and small. The features that would elevate the project to "masterpiece" status are well-defined by what the leading projects (Buzz, CheshireCC, WhisperX) already do — and there is a genuine, unfilled niche at the intersection of yt-dlp and Whisper that no competitor currently owns.

See `ROADMAP.md` for the prioritized plan.
