# Senior Engineering Review — Whisper Project

**Reviewer perspective:** 30+ years building production systems being asked to certify this codebase for long-term maintenance and public release.

**Date:** 2026-05-21
**Branch reviewed:** `release/v0.7.0-installer-3-options` at commit `aa4e33a`
**Reviewer note:** This is a code-and-process review, not a feature review. Praise has been stripped on purpose. The codebase has real strengths (sv_ttk theming, sensible service split, clean Phase 1 modules), but a review whose job is to harden the project must catalogue the failure surface, not the wins.

---

## Executive summary

The project is functionally rich, has solid test coverage (495 passing), and a clean pyright baseline. What it does NOT yet have is **the discipline of a system that has to survive 5+ years of low-effort maintenance by someone who is not the original author.** Concretely:

* The transcription pipeline holds module-level mutable state and routes events between threads / subprocesses with too many implicit assumptions. Worker IPC has at least two paths that can deadlock the Tk main thread.
* Exception handling is uniformly defensive — `except Exception: pass` and `logger.warning("X failed: %s", e)` appear ~80 times. Many silently degrade where they should crash, and many crash where they should retry. The result is a system where a failed transcription often looks like a finished one.
* The repository root has accumulated 6 build artefacts and developer scratch files that signal "private dev workspace", not "production-ready open-source release."
* Documentation has duplicate handoff files, version drift (v0.8 research before v0.7.1 was released), and no top-level `LICENSE` file despite the `pyproject.toml` claiming MIT.

None of these problems are urgent in the "the app is broken" sense. All of them are urgent in the "this will be a maintenance nightmare in 18 months" sense.

The single highest-leverage fix is **adding context to logs** (one afternoon's work; would expose ~60 % of the silent failure paths catalogued below). Everything else can wait.

---

## TASK 1 — Architecture & code quality audit

### Critical (fix before next public release)

#### A1. Worker subprocess `stdin` write can block the Tk main thread

* **Where:** `app/services/transcription_service.py` — the dispatch path that does `worker["process"].stdin.write(json.dumps(command) + "\n")`.
* **Why it matters:** The OS pipe buffer is ~64 KB on Windows. The worker only reads its stdin between tasks, not during transcription. If the parent sends commands while a long task is in flight, eventually the write blocks. That blocks Tk's main thread — the entire UI freezes, with no spinner, no progress, no escape.
* **Failure mode in production:** User queues 20 files. After ~2 minutes the UI locks up. No error. User force-quits, loses queue + history rows. Indistinguishable from a hung model.
* **Fix:** Move stdin writes into a single dedicated writer thread with a `queue.Queue` and per-command timeout. If a write blocks > 5 s, log + kill the worker. This is the same pattern used for shutdown but applied to dispatch.

#### A2. Module-level state in `core/transcriber.py` makes multi-worker semantics non-obvious

* **Where:** `core/transcriber.py:39-52` — `MODEL`, `PIPELINE`, `_ALT_BACKEND`, `_ALT_BACKEND_NAME`, `MODEL_READY`, `MODEL_ERROR` are all module-level mutables.
* **Why it matters:** Workers are spawned as subprocesses, so each worker gets its own copy. That makes the design coincidentally safe today. But the design **looks** like it has process-global state that two threads could trample. A maintainer who adds an in-process worker pool later will silently corrupt the model.
* **Failure mode:** A future contributor implements `parallel_workers > 1` in-process to avoid PyInstaller startup cost. Two transcribe calls race on `MODEL`, the second one starts before the first finishes, and one of them silently uses a different model than its config asked for.
* **Fix:** Move state into a `TranscriberSession` class with explicit lifetime. Keep module-level globals as a thin compatibility shim (existing tests monkeypatch them — that's the only reason they exist) and clearly mark them deprecated in the docstring.

#### A3. History DB row created AFTER worker dispatch

* **Where:** `app/services/transcription_service.py` — `insert_transcription()` runs after the worker has already been told to start.
* **Why it matters:** If history insert fails for any reason (locked DB, disk full, sqlite version skew), the task is running but no row exists. On crash recovery, `mark_interrupted()` finds nothing to mark; the user loses the file from history entirely.
* **Failure mode:** Antivirus locks `history.db` for a single second during dispatch. The insert fails. Worker completes successfully. User looks at History tab — file isn't there. There is no error message. The transcript file exists on disk, but the user doesn't know that.
* **Fix:** Insert the history row FIRST (status=`waiting`), get the row id, pass it to the worker, then dispatch. If insert fails, refuse to dispatch.

#### A4. Worker event routing matches on PID, which the OS recycles

* **Where:** `app/services/transcription_service.py` — `worker_for_event()` checks `worker["id"]` and `process.pid`.
* **Why it matters:** Worker IDs are sequential ints (1, 2, 3…). If worker 1 crashes and a new worker is spawned with id 4, but the OS happens to assign the same PID as the crashed worker 1's PID, a late-arriving event from worker 1 may route to worker 4. Unlikely but possible.
* **Failure mode:** Worker 1 crashes mid-transcription with a Python traceback in its stdout buffer that arrives a few hundred ms late. By then worker 4 has been spawned with a recycled PID. The traceback gets attributed to worker 4's job, marking the wrong file as failed.
* **Fix:** Generate a per-worker `session_token = uuid.uuid4().hex` on spawn; have the worker echo it in every event; route on token, not PID.

#### A5. `_write_outputs` reports success even when zero files were written

* **Where:** `core/transcriber.py` — after the loop, `written` may be empty.
* **Why it matters:** If every requested format failed silently (e.g., one disk-full failure cleaned up all prior writes via the rollback path), the caller logs `"Wrote 0 output file(s):"` and the function returns normally. From the outside, the transcription "finished."
* **Failure mode:** User transcribes a 90-minute meeting. Disk fills mid-write. App reports done. User goes looking for the .srt — nothing on disk. App doesn't know.
* **Fix:** After the loop, if `not written and formats`, raise `RuntimeError("No output files produced — see prior errors")`.

### High severity

#### A6. `transcribe()` is 240 lines and does eight things

* **Where:** `core/transcriber.py:transcribe()`.
* **Why it matters:** Per-folder overrides, runtime config refresh, backend dispatch, Demucs pre-process, VAD param build, segment iteration, post-pipeline (diarisation + alignment + hallucination + chapters), and atomic write — all in one function. Any future change risks accidentally short-circuiting one of those stages. Unit tests can only cover this through mocking.
* **Fix:** Extract `_prepare_runtime_config(task)`, `_dispatch_backend(task, …)`, `_post_process(task, segments)`, `_write_artefacts(task, segments, chapters)`. Each becomes individually testable.

#### A7. Device detection logic duplicated across `transcriber.py` and `backends/faster_whisper_be.py`

* **Where:** `core/transcriber.py:detect_device()` and `core/backends/faster_whisper_be.py:31-49`.
* **Why it matters:** Two near-identical implementations of CUDA / int8 selection. A future fix to one is guaranteed not to land in the other; we've shipped subtle device-mismatch bugs in projects with exactly this pattern.
* **Fix:** Move the canonical detector into `core/hardware.py` (which already exists for the wizard's persisted choice — natural home). Both call sites import from there. Adds one new test boundary, removes one drift hazard.

#### A8. Watcher silently drops files when its callback raises

* **Where:** `core/watcher.py` — the on-event handler swallows callback exceptions.
* **Why it matters:** The watcher feeds files into the transcription queue. If the enqueue fails (history DB write fails, validate path fails, …), the file is dropped. The user has no idea their watched folder is missing files.
* **Fix:** Route callback exceptions onto `app.worker_events` so the UI surfaces them. Worst case, raise a notification: "Watcher dropped X.mp3 — check the log."

#### A9. Soft-fail post-pipeline steps log the failure but mark the run successful

* **Where:** `core/transcriber.py` — diarisation, alignment, hallucination detector, auto-chapters all use the pattern `try: … except Exception as e: log(f"… failed (continuing): {e}", log_cb)`.
* **Why it matters:** The user sees the transcript and assumes everything ran. If diarisation crashed on segment 47, the file is missing speaker labels but nothing in the UI tells the user that. Three months later the user wonders "why are some files diarised and some not?"
* **Fix:** Track which post-pipeline steps were enabled vs. actually completed. Write the answer into the JSON sidecar (`"meta": {"diarisation": "skipped: model missing"}`). Surface a one-line summary in the UI: `Diarisation: skipped — model unavailable.`

#### A10. SQLite reads share connection with concurrent writes; no WAL mode

* **Where:** `core/history.py` — reads (`stats()`, `list_*()`) bypass `_write_lock`.
* **Why it matters:** Long-running reads can see partial writes. `stats()` may return inconsistent counts. With `journal_mode=DELETE` (default), every writer briefly locks the whole DB, so a slow `list_transcriptions(10000)` can starve a concurrent insert.
* **Fix:** Add `conn.execute("PRAGMA journal_mode = WAL")` at open. Acquire `_write_lock` only for writes. Keep the lock for transactions that span multiple statements.

#### A11. Project-override JSON deep-merge has no schema validation

* **Where:** `core/config.py:load_project_overrides()` and the merge into `transcriber.config`.
* **Why it matters:** A user-supplied `.whisperproject.json` with `{"diarization_enabled": "yes"}` survives the merge. The cast at use site is `bool("yes")` which is `True` — looks correct but doesn't mean what the user wrote. Worse: `{"vad_min_silence_ms": "ten"}` will explode much later inside the VAD path.
* **Fix:** Validate the override dict against a hand-rolled type table (`{"diarization_enabled": bool, "vad_min_silence_ms": int, ...}`). Skip + warn for invalid entries; never silently coerce.

### Medium

#### A12. `parallel_workers` spawns new workers per task with no idle reuse

* **Where:** `app/services/transcription_service.py:dispatch_waiting()`.
* **Why it matters:** Worker list grows unbounded across a session. After 100 transcriptions you can have 30 zombie subprocesses (the cleanup path only catches successful completions). Memory leak.
* **Fix:** Cap worker pool at `parallel_workers`. Reuse idle workers. Retire workers idle > 5 minutes (saves model load memory for the user's other apps).

#### A13. Event queues are unbounded

* **Where:** `app/app.py` — `worker_events`, `download_events`, `format_events`.
* **Why it matters:** A storm of progress events from multiple workers can outrun the 100 ms Tk poll, growing the queue without limit. Memory usage rises silently.
* **Fix:** `Queue(maxsize=1000)`. On `Full`, drop oldest event (most progress events are obsolete by the next tick anyway).

#### A14. Pause vs. cancel semantics are racy

* **Where:** `core/transcriber.py` and `core/backends/faster_whisper_be.py` — separate `paused: bool` and `cancelled: bool` flags.
* **Why it matters:** A user who pauses and immediately cancels can hit either order. Undefined behaviour today.
* **Fix:** Replace both flags with a single `task.state` enum (`waiting`, `running`, `paused`, `cancelling`, `cancelled`). Serialise transitions through a method that enforces the legal state machine.

#### A15. Burn-subs path-escape is Windows-shaped on every OS

* **Where:** `core/burn_subs.py:47` — `safe_srt = srt_path.replace("\\", "/").replace(":", "\\\\:")`.
* **Why it matters:** Project documents itself as Windows-first, but tests / future expansion may run on Linux. The replace is a no-op there and the colon escape is wrong for POSIX paths containing colons.
* **Fix:** Branch on `os.name`. On non-Windows, escape only ffmpeg's filter-graph metacharacters (`[]:,;'\\`). Add a unit test for each platform.

#### A16. Implicit Windows-only assumptions in `core/hardware.py` probes

* **Where:** `core/hardware.py` — `_probe_qnn_npu()` returns `[]` on non-Windows but `_probe_openvino()` runs everywhere even though the Intel NPU path is Windows-only.
* **Why it matters:** Linux dev running the wizard sees a spurious OpenVINO NPU tier. Pick it, set `device=cpu`/`compute_type=int8`, and the next transcribe doesn't crash (we fall back) but the user is confused.
* **Fix:** Each probe declares its OS gate up front. Wizard UI greys out tiers that don't apply.

### Low

#### A17. Hardcoded VAD defaults in transcriber when config misses them

* **Where:** `core/transcriber.py:_vad_parameters()` reads `config.get("vad_min_silence_ms", 500)` etc.
* **Why it matters:** Magic numbers inline. Should be `DEFAULT_VAD_PARAMS` in `core/config.py` next to the rest of the defaults so they're tunable.

#### A18. ffmpeg subprocess timeout messages omit input path

* **Where:** `core/diarization.py:114-115` and `core/transcriber.py:get_duration()` timeout branches.
* **Why it matters:** "ffmpeg timed out" without the file path is a debugging dead end.
* **Fix:** Include `audio_path` and the timeout value in the `RuntimeError` message.

#### A19. pywhispercpp version dispatch is by attribute presence, not version string

* **Where:** `core/backends/whisper_cpp.py:210-237` — picks centisecond vs. second by checking `t0` vs `start`.
* **Why it matters:** Fragile — a future pywhispercpp could expose both attributes for backwards compat and silently pick the wrong one.
* **Fix:** Pin the version in `pyproject.toml.optional-dependencies.backend_cpp` and gate on `pywhispercpp.__version__`.

---

## TASK 2 — Debuggability & error system review

### Critical

#### B1. Silent failure is the most common failure mode in this codebase

* **Pattern:** `except Exception as e: logger.warning("X failed: %s", e)` (or just `pass`) appears in roughly 80 places.
* **Why it matters:** Three real classes of bug all reach the user as "nothing happened":
  1. The operation silently succeeded but produced empty output.
  2. The operation crashed but logged at WARNING level which the user never sees.
  3. The operation was skipped because an optional dep was missing, but no UI hint.
  The user-visible difference is zero.
* **Failure mode:** A user reports "transcription doesn't work." There is no error in the UI. The log file shows seven different warnings, none of which point at the root cause.
* **Fix (highest ROI in this whole document):** Adopt one rule, apply everywhere:
  > **Every `except Exception`** must either (a) re-raise after logging with `logger.exception()`, OR (b) surface a user-visible message via `app.log(…)` with a clear "feature X unavailable because Y" framing.
  > **No catch may end in `pass` alone.**
  > **No catch may use `logger.warning("…: %s", e)` — always `logger.exception("…")` when the caught object is an exception.**
* **Effort:** ~3 hours, mechanical sweep. Doubles the diagnostic value of every existing log file.

#### B2. `logger.warning` is used where `logger.exception` is needed

* **Where:** ~30 sites across `core/transcriber.py`, `app/app.py`, `app/services/*.py`.
* **Why it matters:** `warning("foo: %s", e)` loses the stack trace. The user reports a bug, the log shows `WARNING: diarisation failed: ConnectionError`, and there is no way to know where the connection error happened without reproducing it.
* **Fix:** Sweep replace inside every `except` block. `logger.warning` → `logger.exception` whenever the message includes `e`.

#### B3. Background threads swallow exceptions and exit silently

* **Where:** `core/transcriber.py:load_model_async()`, `core/watcher.py` event handlers, `app/widgets/tray.py` tray loop, every `threading.Thread(target=…)` call site.
* **Why it matters:** A daemon thread that raises just dies. No log unless the thread itself remembered to wrap. The user sees the symptom (model never loads, watcher stops firing, tray dies) but not the cause.
* **Fix:** Single helper:
  ```python
  def daemon(target, *args, name=None, **kwargs):
      def _wrapped():
          try:
              target(*args, **kwargs)
          except Exception:
              logger.exception("Daemon thread %r crashed", name or target.__name__)
              raise
      t = threading.Thread(target=_wrapped, name=name, daemon=True)
      t.start()
      return t
  ```
  Replace every `threading.Thread(...).start()` with `daemon(...)`. Mechanical.

#### B4. `_emit_warning` in worker masks the actual serialisation error

* **Where:** `core/worker.py:46-52` — non-JSON-serialisable payloads get `repr()` + a generic warning.
* **Why it matters:** The repr is logged as the payload but the actual `TypeError`/`ValueError` is never logged. When the parent sees `"_emit_warning": "payload was not JSON-serialisable"`, you can't tell what type of value crashed.
* **Fix:** `logger.exception("Worker event payload not JSON-serialisable: %r", payload)` before the fallback.

### High

#### B5. Device / backend / model choice never logged at decision time

* **Where:** `core/transcriber.py:detect_device()`, `load_existing_model()`, `transcribe()`.
* **Why it matters:** Bug reports come in saying "transcription is slow." There is no log line that says **what device was actually used.** The user assumes CUDA, the app fell back to CPU silently, and there is no way to verify either claim from the log file.
* **Fix:** At every decision point, one INFO log:
  * `device=cuda compute_type=float16 source=hardware.json`
  * `backend=faster_whisper model=large-v3 path=...`
  * `hub_folder=… (configured/migrated/default)`
  Five lines total. Saves every future support call.

#### B6. Logs have no task / file context, so parallel runs are unreadable

* **Where:** Almost every log in `core/transcriber.py` and `app/services/transcription_service.py`.
* **Why it matters:** `[42%] 00:01:23 --> 00:01:30 | Hello world` — which file? Which worker? With `parallel_workers=2`, two of these messages interleave and there's no way to attribute them.
* **Fix:** Prefix every log with `[task=<id> file=<basename>]`. Either pass an explicit logger adapter (`logging.LoggerAdapter` with `extra={"task_id": …}`) or prepend the prefix in the `log()` helper.

#### B7. User-facing error strings omit the underlying cause

* **Pattern:** `MODEL_ERROR = f"Backend {backend_name} not available: {e}"` in some places, just `f"{backend_name} load failed"` in others.
* **Why it matters:** Inconsistent. The user sees "failed" with no actionable detail. Support has to ask "what was the exception?" — which the user can't answer.
* **Fix:** Establish one error-string template: `<what was being done> failed: <type>: <message>`. Codify it as a small helper:
  ```python
  def fmt_err(action: str, exc: BaseException) -> str:
      return f"{action} failed: {type(exc).__name__}: {exc}"
  ```

#### B8. No validation that a "ready" model is actually a real model

* **Where:** `core/transcriber.py:load_existing_model()` — sets `MODEL_READY = True` after construction.
* **Why it matters:** `WhisperModel(path)` can return a usable Python object even if the model file is corrupt or partial. The first transcription attempt is where the crash happens, hundreds of lines later.
* **Fix:** After construction, run a 1-second silence probe and verify the model returns at least one segment. Three seconds of startup cost, saves bug reports on corrupt downloads.

#### B9. Retry behaviour is inconsistent across networked operations

* **Where:** `core/model_manager.py` retries the zip download in a loop on checksum failure. `core/backends/whisper_cpp.py:download_default_model()` does NOT retry. `app/observability.py` telemetry post has no retry. yt-dlp wraps its own retry.
* **Why it matters:** Two users on the same flaky Wi-Fi see completely different behaviours depending on which network operation flaked. Hard to debug because the report says "it failed once and now it works" — but only because one path retried and another didn't.
* **Fix:** Centralise on a single `with_retries(fn, attempts=3, backoff=1.5)` helper. Apply uniformly. Document the choice.

### Medium

#### B10. Language detection has no confidence floor

* **Where:** `core/transcriber.py` posts `language_cb(info.language, info.language_probability)` regardless of probability.
* **Why it matters:** A 5 %-confidence "this is Welsh" guess gets used as the SRT language code. The user's English file gets `.cy.srt` and downstream subtitle tools throw it out.
* **Fix:** If `probability < 0.5`, log a WARNING and either skip the language tag or annotate it as low-confidence.

#### B11. Hub folder fallback chain is opaque to the user

* **Where:** `core/config.py:_apply_runtime_fallbacks()`.
* **Why it matters:** Three different fallbacks fire silently: legacy migration, hub-derived path, cache fallback. Log says "model_path unreachable; using fallback X" but doesn't say WHICH fallback fired or whether X exists yet.
* **Fix:** Log the chain explicitly: `model_path=<resolved> source=<explicit|hub_derived|cache_fallback> exists=<bool>`.

#### B12. Recovery from a crashed-mid-transcription state isn't actually exercised

* **Where:** `HistoryDB.mark_interrupted()` flips rows from running → interrupted on launch. App offers to resume.
* **Why it matters:** No test verifies that the resume path actually produces a valid output. The .part file may exist on disk; the writer doesn't know about it and may overwrite it.
* **Fix:** Add an integration test that kills a worker mid-transcribe (SIGTERM at second N), restarts, accepts resume, and asserts the final output matches the un-interrupted reference.

### Low

#### B13. `print(` is used in a few non-test paths

* **Where:** A grep should be run; PyInstaller swallows stdout in windowed mode so these go to a black hole.
* **Fix:** Convert to `logger.info`.

#### B14. `sys.exit()` used outside `gui.py`

* **Where:** Any non-entry-point should raise, not exit. Need to grep.
* **Fix:** Convert to `raise SystemExit(…)` or `raise RuntimeError(…)`.

#### B15. Observability fallbacks return empty / False on exception

* **Where:** `app/observability.py:_telemetry_opted_in()`, `_anonymised_id()`, `_app_version()`.
* **Fix:** `logger.warning("telemetry config probe failed: %s", e)` before returning the fallback.

---

## TASK 3 — Repository & branch presentation

### Critical

#### C1. No `LICENSE` file at repo root

* **Reality:** `pyproject.toml` declares `license = "MIT"`. `README.md` says "Unspecified." There is no `LICENSE` file at root.
* **Why it matters:** Without `LICENSE`, the code is **legally unredistributable** by default in many jurisdictions. GitHub will show "No license" badge. Cannot accept PRs cleanly. Cannot bundle binary releases without warranty disclaimer.
* **Fix:** Copy the standard MIT `LICENSE` text to `<repo_root>/LICENSE`, with the project's author / year. Update `README.md` license section to match. **One-minute fix, blocking for public release.**

#### C2. Duplicate handoff docs

* **Reality:** `docs/SESSION_HANDOFF_NEXT.md` (current) and `docs/HANDOFF_NEXT_SESSION.md` (older, stale) both exist. The older one is marked stale but is still discoverable. `CLAUDE.md` references the older filename in one place.
* **Why it matters:** A new contributor opens the wrong file and acts on outdated instructions.
* **Fix:** Delete `docs/HANDOFF_NEXT_SESSION.md`. Sweep `CLAUDE.md` and any other reference. Add a `docs/README.md` that points unambiguously at the current one.

### High

#### C3. Root directory looks like a private dev workspace

* **Reality:** Root contains `build.bat`, `build_embed_installer.bat`, `installer.iss`, `installer_embed.iss`, `whisper_project_onefile.spec`, `whisper_project_onedir.spec`, `config.json.migrated.bak`, `dist/`, `dist_onedir/`, `dist_installer/`, `embed_build/`, `build_logs/`.
* **Why it matters:** First impression on the GitHub landing page is "scratch directory", not "open-source project." A new contributor cannot easily distinguish source from artefacts.
* **Fix:** Adopt this layout:
  ```
  ./LICENSE
  ./README.md
  ./CONTRIBUTING.md
  ./CHANGELOG.md       (move from docs/)
  ./CLAUDE.md
  ./pyproject.toml
  ./requirements.txt
  ./gui.py
  ./app/
  ./core/
  ./tests/
  ./bin/
  ./docs/              (everything else current docs/* lives here)
  ./packaging/
      ./build.bat
      ./build_embed_installer.bat
      ./installer.iss
      ./installer_embed.iss
      ./whisper_project_onefile.spec
      ./whisper_project_onedir.spec
      ./README.md      (how to build each deliverable)
  ./.build/            (gitignored; dist/, dist_onedir/, dist_installer/, embed_build/, build_logs/)
  ```
* **Side effect:** Update `build.bat` / `build_embed_installer.bat` to `cd ..` before invoking PyInstaller so the spec paths still resolve. Update `.gitignore` to ignore `.build/`.

#### C4. No `CONTRIBUTING.md` or `CODE_OF_CONDUCT.md`

* **Reality:** Both absent. Project has CI, releases, optional deps for backend choices — all the trappings of a project that accepts contributions, except the docs that tell people how.
* **Fix:** Add `CONTRIBUTING.md` that covers:
  * how to set up the dev environment (link to `docs/INSTALL.md`)
  * how to run tests (`pytest tests/ --ignore=tests/smoke`)
  * how to run pyright (`pyright app/ core/`)
  * commit message style (link to existing convention)
  * PR process
  * how to report bugs (link to GH issues)
  Add a short `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 is the standard).

#### C5. Version drift between code, docs, and download links

* **Reality:** `pyproject.toml` says `version = "0.7.1"`. README hard-codes v0.7.1 in three asset download URLs. `docs/V08_FEATURE_RESEARCH.md` and `docs/V09_REMOTE_MODE_RESEARCH.md` describe v0.8 features as planned. But this branch already SHIPPED Phase 1+2+3 of v0.8.
* **Why it matters:** A maintainer six months from now cannot tell whether v0.8 is shipped or pending. Re-doing landed work is the most common cost of version drift.
* **Fix:**
  1. Bump `pyproject.toml` to `0.8.0-dev` or `0.7.2-dev` reflecting the in-progress state.
  2. Move `V08_FEATURE_RESEARCH.md` and `V09_REMOTE_MODE_RESEARCH.md` into `docs/roadmap/` with a clear `README.md` explaining "this folder = future work; everything in docs/ root = current state."
  3. Add a status box at the top of `V08_FEATURE_RESEARCH.md`: `Phase 1: SHIPPED at fb45094. Phase 2: SHIPPED at 99af9bf. Phase 3: SHIPPED at 99af9bf.`

#### C6. `BUILD.md` is out of date and possibly truncated

* **Reality:** Says Portable ~190 MB but the v0.7.1 Portable is 447 MB (per `SESSION_HANDOFF_NEXT.md`). Last few sections may be cut off.
* **Fix:** One pass on `BUILD.md`. Update sizes. Verify every numbered step still works. Add a "tested on $(date)" footer.

#### C7. `docs/history/` is cluttered and undocumented

* **Reality:** 13 files including a `.spec` file (`WhisperProjectDebug.spec`), no README explaining what / why / retention policy.
* **Fix:** Add `docs/history/README.md`: "Archive of acceptance + brief docs from v0.7 development cycles. Retained for audit trail. Current state lives in docs/SESSION_HANDOFF_NEXT.md." Move the `.spec` file to `packaging/` or delete if obsolete.

### Medium

#### C8. Inconsistent doc filename conventions

* **Reality:** Mix of `UPPERCASE.md`, `UPPERCASE_WITH_UNDERSCORES.md`, and `kebab-case.md`.
* **Fix:** Pick one. `UPPERCASE.md` for the canonical, top-level docs (README, LICENSE, CHANGELOG, BUILD, INSTALL, ARCHITECTURE) — these are filesystem conventions readers expect. `Title_Case.md` for everything else. Rename `architecture-diagrams.md` → `ARCHITECTURE_DIAGRAMS.md`, `auto-subtitles-feature.md` → `AUTO_SUBTITLES.md`.

#### C9. No `docs/README.md` (navigation guide)

* **Reality:** `docs/` has 21 files. No table of contents.
* **Fix:** One short `docs/README.md`:
  ```markdown
  # Documentation index

  **Start here**
  - [INSTALL.md](INSTALL.md) — end-user install instructions
  - [ARCHITECTURE.md](ARCHITECTURE.md) — how the app is wired together
  - [BUILD.md](BUILD.md) — how to produce the EXE / installer

  **Reference**
  - [CONFIG.md](CONFIG.md) — every config key explained
  - [CHANGELOG.md](../CHANGELOG.md) — version history
  - [DECISIONS.md](DECISIONS.md) — non-obvious design choices + their why

  **Roadmap / WIP**
  - [roadmap/](roadmap/) — future features still on paper

  **Internal**
  - [SESSION_HANDOFF_NEXT.md](SESSION_HANDOFF_NEXT.md) — current dev state
  - [history/](history/) — archived session notes
  ```

#### C10. `SESSION_HANDOFF_NEXT.md` mixes durable rules with tactical state

* **Reality:** Section 4 ("User preferences learned this session") contains durable rules already mostly in `CLAUDE.md`.
* **Fix:** Anything intended to persist across sessions belongs in `CLAUDE.md` (durable, auto-loaded). The handoff doc should be ~80 lines max: current state + immediate next task + 1-line restart prompt.

#### C11. `requirements.txt` carries 16 lines of historical commentary

* **Reality:** Lots of "Phase 1 added X" / "Phase 2 added Y" inline comments.
* **Fix:** Strip down to active dependency lines + a single header note pointing at `pyproject.toml` for optional-dep groups. Move history into `CHANGELOG.md` or `docs/DEPENDENCIES.md`.

### Low

#### C12. No screenshots in README

* **Fix:** Add one 600 px-wide screenshot of the Transcribe tab. Or a 5-second GIF of drag-and-drop. Massive bump to perceived professionalism on the GH landing page.

#### C13. `config.json.migrated.bak` at root

* **Fix:** Either delete (if it's a stale developer artefact) or document and move to `docs/examples/`.

#### C14. Build artefact directories tracked in git status

* **Fix:** Confirm `.gitignore` actually ignores `dist/`, `dist_onedir/`, `dist_installer/`, `embed_build/`, `build_logs/`. If any of these have ever been committed, they should be excluded going forward.

---

## TASK 4 — Hardening & production readiness

### Critical

#### D1. `save_config` race when two threads write at once

* **Status:** Already mitigated (`_SAVE_LOCK` in `core/config.py`). Verified during this review. Good.
* **Gap:** `save_config` writes the WHOLE config every time. If the user is editing the config (via a hand-edit in another app) and the program also writes, the program clobbers user edits.
* **Fix:** Atomic read-modify-write: re-read the on-disk config inside the lock, apply only the keys that changed, write. Or document loudly that hand-edits aren't supported while the app is running.

#### D2. `history.db` open at App init has no journal-mode set

* **Where:** `core/history.py:HistoryDB.__init__`.
* **Why it matters:** Default `journal_mode=DELETE` means a crash mid-write can leave the DB in a state the next launch refuses to open (rare but possible). With WAL, recovery is automatic.
* **Fix:** `conn.execute("PRAGMA journal_mode=WAL")` and `conn.execute("PRAGMA synchronous=NORMAL")` after open. Run once per connection.

#### D3. Model download integrity check is MD5

* **Reality:** `core/model_manager.py` downloads + verifies the model zip via MD5.
* **Why it matters:** MD5 is fine against bit-flips but not against a hostile mirror. For a system that downloads multi-GB binaries from a third-party URL on first launch, this is the kind of thing a security review will flag.
* **Fix:** Switch to SHA-256. Publish the manifest signed (or at least pinned in the source code). Document threat model in `docs/SECURITY.md`.

#### D4. No SECURITY.md / disclosure policy

* **Reality:** Project has no security contact or disclosure process.
* **Fix:** Add `SECURITY.md` at root: "Report security issues to <email>; we respond within 7 days." Mention bundled-binary trust boundary.

### High

#### D5. Subprocess termination is best-effort

* **Where:** `app/services/transcription_service.py:stop_all()`, worker shutdown paths.
* **Why it matters:** If the worker subprocess is mid-CUDA-kernel, terminate() may leave a stale GPU allocation. Next launch's CUDA init may fail.
* **Fix:** Use a structured shutdown protocol: send `{"cmd": "shutdown"}` via stdin, wait up to 10 s, then `terminate()`, then `kill()`. Log each step.

#### D6. No corruption check on history.db at startup

* **Fix:** `conn.execute("PRAGMA integrity_check")`. If it fails, rename to `history.db.corrupt`, recreate fresh, log a WARNING the user sees in the UI.

#### D7. `config.json` corruption recovery exists but isn't validated

* **Where:** `core/config.py:load_config()` renames corrupt files to `.corrupt`.
* **Gap:** No test covers the corruption path beyond the JSON decode case. UnicodeDecodeError + permission errors are handled but not tested.
* **Fix:** Add unit tests for: cp1252-encoded config, permission-denied on read, partial JSON write (object truncated mid-string).

#### D8. Worker crash doesn't tear down associated state cleanly

* **Where:** When a worker subprocess crashes mid-task, the task stays at status=`running` until the next launch's `mark_interrupted()` pass.
* **Why it matters:** The UI shows the task as running. The progress bar freezes. The user has no way to know the worker died.
* **Fix:** Heartbeat. Worker emits `{"type": "heartbeat"}` every 5 s. Parent watches; if 30 s elapse with no heartbeat, mark the task failed and log.

#### D9. ffmpeg subprocess holds open pipes on early timeout

* **Where:** `core/transcriber.py:get_duration()` etc.
* **Fix:** Use `Popen(...).communicate(timeout=N)` consistently rather than `run()` so pipes always close.

### Medium

#### D10. No "safe mode" launch option

* **Why it matters:** If the user's config or hub folder is broken in a way that prevents startup, they have to delete files by hand to recover.
* **Fix:** Recognize a `--safe-mode` CLI flag that ignores `config.json` (uses defaults), skips model autoload, and presents a "your config has been backed up; pick what to keep" UI.

#### D11. No memory cap for transcribe segments list

* **Why it matters:** A 12-hour audio file with word-level timestamps holds the entire `segments_data` in memory. On low-RAM systems this can OOM.
* **Fix:** For files > N minutes, stream segments to disk and reload at write time instead of holding them in memory.

#### D12. No platform-version compatibility check at startup

* **Why it matters:** Bundled CUDA wheels target a specific Python ABI. If the user runs the source build on Python 3.13 while the embed installer was built for 3.11, the user gets a confusing import error.
* **Fix:** At startup, log `python_version=…`, `pyinstaller=…`, `ctranslate2=…`. If running outside the supported matrix, warn.

#### D13. No test for installer Pascal Script on a real Inno Setup compile

* **Where:** `tests/core/test_inno_uninstall_parser.py` mirrors the logic in Python — good. But the actual `.iss` is never compiled in CI.
* **Fix:** Add a CI step that runs Inno Setup's compiler in lint mode if available; otherwise document the manual compile step before each release.

### Low

#### D14. Telemetry opt-in default is False (good) but never tested

* **Fix:** Add a smoke test that constructs the telemetry payload without sending it, verifying the field shape.

#### D15. Crash reporter (Sentry) DSN is read from env, not config

* **Fix:** Document this in `docs/CONFIG.md`.

---

## TASK 5 — Documentation & knowledge architecture

### High

#### E1. There is no single "what is this project, in 3 sentences" answer

* **Reality:** `README.md` jumps into download links before establishing context.
* **Fix:** Open `README.md` with:
  > **Whisper Project** is a Windows desktop app that transcribes audio and video files locally using OpenAI's Whisper model. Drag a file in, get an .srt + .json + .docx back. No cloud, no account.
  > Ships as: portable single-EXE, compact installer, or standard installer with embedded Python.
  Three sentences. Anything else is detail.

#### E2. No `ARCHITECTURE.md` walkthrough that maps the actual code

* **Status:** Doc exists, content unknown to this reviewer. Likely needs a one-page diagram showing:
  * gui.py → App → services (Transcription, Download, Format, Integrations)
  * Transcription service → worker subprocess (one per parallel slot)
  * Worker → core/transcriber → backend → writers + sidecars
  * History DB / search.db / voices.db / config.json / hardware.json — what writes each, what reads each.
* **Fix:** Spend two hours producing one ASCII diagram + a 1-page narrative.

#### E3. `docs/DECISIONS.md` (if it exists) needs entries for the recent Phase 1-3 work

* **Items that have no recorded rationale:**
  * Why `hub_folder` as a separate key from `model_path`
  * Why download-on-first-use for the LLM model instead of bundling
  * Why Parakeet uses a separate backend instead of being a Whisper-model slug
  * Why auto-chapters live in a sidecar JSON, not in the main JSON
* **Fix:** One entry per decision, ~10 lines each.

#### E4. No troubleshooting / FAQ doc

* **Fix:** Create `docs/TROUBLESHOOTING.md` covering:
  * "Model download keeps failing" → check disk space, MD5 mismatch fallback
  * "Transcription is on CPU, I have a GPU" → check `hardware.json`, run wizard
  * "No output files appeared" → check disk space, check log for write errors
  * "Diarisation isn't running" → check `diarization_enabled`, check pyannote install
  * "App won't start" → run with `--safe-mode` once that exists
  Five problems × five lines each = 25 lines of doc that probably handles 80 % of support requests.

### Medium

#### E5. Knowledge is scattered between `CLAUDE.md`, `SESSION_HANDOFF_NEXT.md`, and prose paragraphs in source

* **Fix:** `CLAUDE.md` holds durable design choices. `SESSION_HANDOFF_NEXT.md` holds only "where to pick up next." `ARCHITECTURE.md` holds the system shape. `DECISIONS.md` holds the why. Each piece of knowledge lives in exactly one place, with links from the others.

#### E6. No mental model for the test taxonomy

* **Fix:** `tests/README.md` covering:
  * `tests/core/test_*.py` — unit, run on every commit
  * `tests/core/test_transcribe_smoke.py` + `test_transcribe_end_to_end.py` — need real model
  * `tests/core/test_v08_real_file_e2e.py` — need real model + SMTV fixture
  * `tests/smoke/` — needs network + real model + SMTV
  * How to skip the slow ones in dev (`--ignore`).

#### E7. No public changelog gating

* **Fix:** `CHANGELOG.md` exists but isn't enforced. Add a CI check that every PR touches `CHANGELOG.md` (unless labelled `no-changelog`).

### Low

#### E8. No "how this app starts up" sequence diagram

* **Fix:** Add to `ARCHITECTURE.md`. Captures the order: load_config → migrate → first-run hub dialog → model standby → tray → watcher → tk.mainloop.

#### E9. No example transcripts in the repo

* **Fix:** Commit a tiny sample audio + its expected JSON / SRT in `examples/`. Doubles as a manual sanity check.

---

## Prioritized action plan

### Sprint 1 — critical, ~1 day of work

These are the items that block a clean public release or that have user-visible failure modes today:

1. **Add `LICENSE` at root** (C1). 1 minute.
2. **Delete `docs/HANDOFF_NEXT_SESSION.md`, update CLAUDE.md reference** (C2). 5 minutes.
3. **Sweep `except` blocks: every catch logs with `logger.exception` or surfaces a user message** (B1, B2, B3). 3 hours, mechanical.
4. **Move worker stdin writes off the Tk thread** (A1). 1 hour + integration test.
5. **Insert history row BEFORE worker dispatch** (A3). 30 minutes + test.
6. **Log device / backend / model choice at decision time** (B5). 30 minutes, 5 INFO lines.
7. **Raise `RuntimeError` when `_write_outputs` produced zero files** (A5). 5 minutes + test.
8. **Add daemon-thread wrapper that logs crashes** (B3). 30 minutes + grep-and-replace.

Total: ~6 hours focused work. Each delivers a measurable reduction in either silent-failure risk or release-blocking gap.

### Sprint 2 — high-value, ~3 days

9. **Move build artefacts + spec / installer files into `packaging/` + `.build/`** (C3). 2 hours including doc updates.
10. **Add `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`** (C4, D4). 1 hour.
11. **Add `docs/README.md` navigation guide** (C9). 30 minutes.
12. **Fix version drift: bump `pyproject.toml`, label v0.8 research as shipped, move roadmap to subdirectory** (C5). 1 hour.
13. **Add per-task log prefix `[task=… file=…]`** (B6). 1 hour, via LoggerAdapter.
14. **Establish error-string template helper + sweep call sites** (B7). 2 hours.
15. **Centralise device detection in `core/hardware.py`** (A7). 2 hours including test moves.
16. **Add `PRAGMA journal_mode=WAL` + integrity check on history.db** (A10, D2, D6). 1 hour.
17. **Add worker heartbeat + auto-fail on missing heartbeat** (D8). 4 hours.
18. **Add `SAFE_MODE` CLI flag** (D10). 2 hours.
19. **Refactor `transcribe()` into smaller functions** (A6). 4 hours.

Total: ~3 working days.

### Sprint 3 — optional refinements, do when bandwidth allows

20. **Worker session token instead of PID** (A4).
21. **Cap event queues** (A13).
22. **Replace pause/cancel bools with state enum** (A14).
23. **Validate project-override JSON against a schema** (A11).
24. **Add `docs/TROUBLESHOOTING.md`, `docs/DEPENDENCIES.md`** (E4, C11).
25. **Streaming segments to disk for very long files** (D11).
26. **Add screenshot to README** (C12).
27. **Move device detection + retry helper into reusable utilities** (B9).

### Items deferred — discuss before doing

These are real issues but the right fix isn't obvious without product judgement:

* MD5 → SHA-256 for model integrity (D3). Need to coordinate with the model-mirror infrastructure.
* Whether to actually retire `model_path` in favour of `hub_folder` everywhere, or keep the override semantics indefinitely.
* Whether to bundle the LLM model (large) or keep download-on-first-use (current design).
* Whether to add NSIS alongside Inno Setup (vendor-lock-in trade-off).

---

## What this codebase already does well — kept terse

Per the brief, the review prioritized weak points. For completeness:

* `core/hub.py` (just landed in this session) is a clean example of how a small module with clear single responsibility, type hints, and Tk-free design should look. **Use it as the template for refactors below.**
* `core/hardware.py` + its persistence pattern (`.tmp` + `os.replace`, `.corrupt` rename on bad parse) is exactly the right shape for safe filesystem state.
* Test coverage is genuinely good — 495 tests is more than most projects at this maturity ship with.
* `pyright` clean baseline is rare and valuable. **Protect it.** Add a CI gate that breaks any commit that introduces a pyright error.
* CLAUDE.md as an auto-loaded durable rules file is the right pattern. Keep it.

---

## How to use this document

* The Action Plan is sequenced. Do Sprint 1 first. Don't pick item 20 before doing item 1.
* Each finding has a file:line reference so you can verify the issue still exists before fixing it.
* If a finding turns out to be already fixed (the codebase moves fast), strike it out with a brief note — don't delete it; the audit trail matters.
* Save this file. Six months from now, run the same review again, diff against this one. Items that survived two reviews are the real technical debt.

---

*End of review.*
