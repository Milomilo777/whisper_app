# Deep audit brief — senior-architect, line-by-line, agentic

You are a **senior software architect** doing a meticulous, line-by-line
quality + robustness + bug audit of this entire project, and fixing what you
find. Work **agentically**: fan out parallel read-only audit shards by
concern, collect their findings, then fix in batches yourself. Leave the
project measurably more bulletproof, with **zero known bugs**.

Read first, in order: this file, `CLAUDE.md`, `docs/SESSION_HANDOFF_NEXT.md`.
They define the durable rules; obey them. Highlights you MUST respect:

- **Single mainline `master`.** Commit LOCALLY and often (lose nothing), but
  **push in batches** (several related commits together — owner's request).
- **Gate before every commit:** `pyright app/ core/` = **0/0/0**, and the
  hermetic suite (`tests/` minus `tests/smoke/`) green. Never regress these.
- **Git identity is `translation-robot`** (the program's author); never
  reintroduce a personal email or any `Co-Authored-By` trailer in commits.
- **Release policy:** prune old releases, keep ONLY the latest (+ `basic-v0.1.0`);
  release infrequently. Don't cut a version per fix — batch them.
- **Windows is the shipped, testable platform.** macOS/Linux code is correct-
  by-reasoning but UNVERIFIED on real hardware — don't claim otherwise.

## How to work (method)

1. **Fan out audit shards in parallel** (Agent tool, run_in_background,
   read-only — they REPORT, they don't edit). Scope each to one concern so
   findings are atomic. Suggested shards (add/split as needed):
   - **Concurrency & lifecycle:** the worker subprocess + cooperative
     cancel/pause/resume, queue dispatch, the liveness watchdog, tray,
     `after()` loops, thread-safety of Tk access, shutdown ordering, races.
   - **Resource leaks:** orphaned grandchild ffmpeg/demucs processes (no
     process-group/job-object kill), the `partials/` checkpoint dir growing
     unbounded + no startup sweep, HistoryDB connection not closed on exit,
     temp files, file handles, the demucs cache.
   - **Security / hostile input:** re-verify the yt-dlp `--` end-of-options
     guard + zip-slip guard hold; hunt path traversal, crafted filenames,
     the deferred `burn_subs` `subtitles=` filter escaping (only `\`/`:`
     escaped, not `'[],`), and any `shell=True`/`eval`/`os.system`.
   - **Error handling / degradation:** missing binaries (ffmpeg/ffplay/yt-dlp),
     no network, optional-dep install failures (partial installs), bad config,
     corrupt model, full disk — does each fail loudly + safely, never silently?
   - **Data integrity:** checkpoint/resume correctness, output-writer
     atomicity + the per-format resilience, config save/load round-trip,
     history DB writes, de-dup naming.
   - **Cross-platform (Win/Linux/macOS):** confirm the recent platform work
     didn't regress Windows; re-check `os.name`/`sys.platform` branches,
     binary resolution, the Mac/Linux scripts (`bash -n`) and the Homebrew
     formula + PyInstaller spec for correctness-by-reasoning.
   - **Test-coverage gaps:** the deferred P1–P5 (transcribe-tab clip wiring
     end-to-end, crash-resume dispatch, watched-folder, Advanced-settings
     round-trip, SMTV format→command) + anything thinly covered.
   - **Maintainability / type-safety:** dead code, duplicated logic, stale
     docs/comments, and tighter pyright (consider `standard` mode locally to
     surface latent issues — but the SHIPPED gate stays `basic` 0/0/0).
   Each shard returns prioritized `[P0/P1/P2]` findings with `file:line` + a
   one-line fix. Tell them: research with the web where useful; do NOT edit.

2. **Triage + fix yourself, in batches.** Group fixes by theme; one coherent
   change per local commit; gate (pyright + hermetic suite) after each batch;
   push batches, not single commits.

3. **Prove the risky ones.** For concurrency / cancel / output / cross-cutting
   fixes, add a hermetic test AND, where it touches the real worker, run the
   live drivers: `tools/e2e_slim_pastbugs.py` and `tools/e2e_cancel_pause.py`
   (need the model + the test video at `E:\3029-NWN-Daily-Scroll-2m_0002.mp4`).

4. **Known starting points** (already triaged, may still need work): the
   deferred items at the bottom of `docs/SESSION_HANDOFF_NEXT.md` §3, and
   `docs/AUDIT_2026-05-25_boundary_bugs.md`. Re-check; don't assume fixed.

## When to build / release

Only if fixes change shipped behavior AND enough has accumulated (per the
"release infrequently" rule). Then follow `docs/SESSION_HANDOFF_NEXT.md` §3
(bump version in 4 files → slim build → ISCC → Portable zip → past-bug E2E →
publish → **prune the previous release**). Update the handoff + CHANGELOG.

## Definition of done

pyright 0/0/0 + hermetic suite green; every shard finding either fixed or
explicitly logged as deferred-with-reason in the handoff; new tests for the
real fixes; `docs/SESSION_HANDOFF_NEXT.md` updated with what changed and
what remains. Be honest about anything unverifiable (macOS/Linux on real HW).
