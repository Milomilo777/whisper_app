# Final freeze-pass audit — 2026-05-21

**Branch:** `chore/cleanup-hardening` at commit `8f1aff3`
**Context:** project is being distributed **privately** to a small group of
users — not published to the public internet. Items that only matter
for OSS publication (LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md) are
deliberately out of scope.

## TL;DR

Branch is **not yet** ready to freeze. Eight concrete gaps remain.
Five are small (~1 hour each). Three are moderate (~half a day each).
None requires architecture work.

If you fix only the five small gaps, the branch becomes **safe to use
in production for a small audience**. If you fix all eight, it
becomes **safe to walk away from for 6+ months and inherit cleanly**.

---

## Remaining risks

### R-1 · The flaky `test_hub_setup_dialog` test

Severity: **Medium**

This test passes when run alone, fails ~30% of the time when run with
the full suite. It only touches Tk grab_set + a withdrawn root, so
the failure isn't dangerous, but a flaky test in CI conditions every
contributor to "just re-run" — which masks real flakes.

* **Concrete fix:** add a 50 ms sleep before `grab_set()`, or
  monkeypatch the `transient(master)` call out in the test.
* **Effort:** 30 min including investigation.

### R-2 · Partial except sweep

Severity: **Medium**

Of ~80 `except Exception` blocks, only 10 were converted to
`logger.exception()`. The other 70 either swallow silently or use
`logger.warning(... %s, e)` which loses the stack trace.

* **Concrete fix:** module-by-module pass. Each module is ~5-20
  except sites; per-module commit. The sweep itself is mechanical
  but should be done with care so cleanup-path swallows (intentional)
  are preserved.
* **Effort:** ~2-3 hours total, splittable into 6-8 small commits.

### R-3 · No daemon-thread migration

Severity: **Medium**

`core/_threads.py:safe_thread()` exists (Round 1 of this session)
but the ~10 existing `threading.Thread(target=...)` call sites
were not migrated. New code can use the safe wrapper; old code
still loses exceptions silently.

* **Concrete fix:** grep + replace each call site individually,
  one commit per file. Many call sites already have local
  try/except handling, so the migration is mostly cosmetic — the
  benefit is having one place to centralize crash-logging policy.
* **Effort:** ~1 hour total.

### R-4 · No crash-resume integration test

Severity: **High** (for the freeze, anyway)

`HistoryDB.mark_interrupted()` flips rows to interrupted on launch.
The App offers to resume those tasks. **There is no test** that
this resume path actually produces a valid output. If the resume
logic regresses, the user loses data on every crash.

* **Concrete fix:** add a test that
  1. starts a transcribe
  2. kills the worker subprocess at N seconds
  3. relaunches the App
  4. accepts the resume prompt
  5. asserts the final JSON matches the reference
* **Effort:** ~half a day. Touches multiple layers; non-trivial.

### R-5 · No `--safe-mode` CLI flag

Severity: **Low** (but useful for support)

If a user's config or hub folder is broken in a way that prevents
startup, today they have to delete files by hand. A `--safe-mode`
flag would: ignore `config.json`, skip model autoload, use the
default hub path, present a "your config has been backed up" UI.

* **Concrete fix:** add to `gui.py` early-arg-parse; touches one
  file in core (`config.py:load_config` accepts a `safe_mode`
  parameter that bypasses the file read).
* **Effort:** ~1 hour.

### R-6 · Three deliverables never built on this branch

Severity: **High** (real release blocker)

PyInstaller specs + Inno Setup `.iss` files were edited
(hub folder added, hidden imports updated, uninstall logic added)
but the actual builds have never been produced on this branch. The
spec / installer scripts could be subtly broken.

* **Concrete fix:** run all three build flows locally:
  1. `pyinstaller whisper_project_onefile.spec` → Portable
  2. `pyinstaller whisper_project_onedir.spec` → onedir build
  3. `ISCC.exe installer.iss` → Setup-Compact
  4. `ISCC.exe installer_embed.iss` → Setup-Standard
  Each output should be smoke-tested on a fresh Windows user
  profile (delete `%LOCALAPPDATA%\WhisperProject` between runs).
* **Effort:** ~half a day including the install/uninstall walks.

### R-7 · No manual install/uninstall test on this branch

Severity: **High** (paired with R-6)

The Inno Setup uninstall hub-folder prompt logic (commit `aa4e33a`)
has tests for the Pascal-Script parsing logic in Python, but the
actual `.iss` files have never been compiled and the resulting
installer has never been run.

* **Concrete fix:** as part of R-6, install each setup variant
  twice — once with hub folder inside `{app}`, once with hub on
  `D:\`. Uninstall and confirm the prompt fires only for the
  D:\ case and only deletes when the user clicks Yes.
* **Effort:** included in R-6's half day.

### R-8 · `docs/RELEASE_PROCESS.md` does not exist

Severity: **Medium**

The freeze + release process is documented across `CLAUDE.md`,
`SESSION_HANDOFF_NEXT.md`, and `EXECUTION_ROADMAP.md`. A maintainer
six months from now needs ONE document with the exact steps.

* **Concrete fix:** write a short `docs/RELEASE_PROCESS.md` —
  ~50 lines — covering: bump version, build three deliverables,
  test, write release notes, tag, upload, archive branch.
* **Effort:** ~45 min.

---

## Polish opportunities

These are NOT blockers. Land them if you have spare bandwidth.

### P-1 · README opener
README has no "what is this?" paragraph at the top. A reader has to
scroll past download links to find out it's a Whisper desktop app.
Two sentences would fix it.

### P-2 · One screenshot
A 400 px screenshot of the Transcribe tab in the README would do
more to convey the app's purpose than 90 lines of prose.

### P-3 · Verify `ARCHITECTURE.md` is current
The file exists but its contents weren't reviewed in this audit.
Confirm it still reflects the current shape (services / widgets /
core split + worker subprocess model).

### P-4 · Tests README
`tests/README.md` would explain the three test tiers
(unit / unit+E2E / unit+E2E+smoke+manual) so a new contributor
knows what to run.

---

## Documentation gaps

| Gap | Effort | Priority |
|---|---|---|
| RELEASE_PROCESS.md (R-8 above) | 45 min | High |
| TROUBLESHOOTING.md / FAQ | 1-2 hours | Medium |
| `tests/README.md` test taxonomy | 30 min | Low |
| Verify ARCHITECTURE.md still current | 30 min | Medium |
| Add docs/SECURITY.md (threat model for bundled binaries) | 1 hour | Low (private distro) |

---

## Production risks (unchanged from earlier reviews)

The audit `SENIOR_REVIEW_2026-05-21.md` catalogued these. Status check:

| Item | Status |
|---|---|
| Worker stdin can block Tk | **Fixed** (Round 4) |
| History row inserted after dispatch | **Fixed** (Round 4) |
| Stale event routing via PID recycle | **Fixed** (Round 4) |
| Worker death goes undetected | **Fixed** (Round 4) |
| Config writes can race | Not fixed — current code is OK for single-user use; full atomic RMW deferred |
| MD5 model integrity | Not fixed — needs mirror coordination |
| Module-level transcriber state | Not fixed — current subprocess isolation makes the risk theoretical |
| Long files OOM | Not fixed — needs streaming refactor |

The fixed items remove the biggest production risks. The remaining
items have known mitigations (single-user, current scale, etc.) so
they're safe to defer.

---

## Maintainability concerns

### M-1 · The flaky test (R-1)
Stays here under maintainability too — flaky tests rot a project.

### M-2 · `app/app.py` is ~1500 lines
The App class is a monster. Future contributors will be intimidated.
Not blocking, but the "split into mixins or service objects" refactor
will be inevitable around the 2000-line mark. Worth keeping it in
mind.

### M-3 · Two specs to keep in sync
`whisper_project_onefile.spec` and `whisper_project_onedir.spec` have
duplicate hidden-import lists. Every new module = update both. Easy
to forget. A shared `_hidden_imports.py` imported by both specs would
remove the duplication, but PyInstaller spec files are awkward to
factor. Acceptable as-is given the slow rate of new modules.

### M-4 · `requirements.txt` vs `pyproject.toml` drift potential
Both list runtime deps. `pyproject.toml` is the canonical source via
`[project.optional-dependencies]` but `requirements.txt` is what most
pip flows use. Periodic manual sync needed. Document in
RELEASE_PROCESS.md.

---

## Freeze checklist

Run top to bottom. Skip nothing.

- [ ] R-1: Investigate + fix the flaky `test_hub_setup_dialog` test
- [ ] R-2: Complete the except-block sweep (logger.exception)
- [ ] R-3: Migrate the 10 existing `threading.Thread` sites to `safe_thread`
- [ ] R-4: Add a crash-mid-transcribe → resume integration test
- [ ] R-5: Add `--safe-mode` CLI flag
- [ ] R-6: Build all three deliverables locally
- [ ] R-7: Manual install + uninstall walk on fresh profile (each variant + each hub-folder location)
- [ ] R-8: Write `docs/RELEASE_PROCESS.md`
- [ ] `pyright app/ core/` → 0 errors, 0 warnings
- [ ] `pytest tests/ --ignore=tests/smoke` → all green, no flakes on 3 consecutive runs
- [ ] `tests/core/test_v08_real_file_e2e.py` → 10/10 on a fresh `%LOCALAPPDATA%\WhisperProject`
- [ ] `pytest tests/core/test_transcribe_smoke.py tests/core/test_transcribe_end_to_end.py` → 7/7
- [ ] Hub-folder first-run dialog visually tested on a fresh user profile
- [ ] `docs/SESSION_HANDOFF_NEXT.md` updated with the freeze state
- [ ] `pyproject.toml` version bumped to release candidate (`0.8.0-rc1`)

## Release checklist (for the private distribution)

Run after the freeze checklist passes.

- [ ] CHANGELOG.md entry written
- [ ] `RELEASE_NOTES_v0.8.0.md` written — summarise what changed since v0.7.1
- [ ] All three EXEs produced + smoke-tested
- [ ] Each EXE uploaded to wherever the private distribution lives (Drive folder, internal share, etc.)
- [ ] Recipients informed (your existing distribution channel)
- [ ] Tag `v0.8.0` pushed
- [ ] `chore/cleanup-hardening` branch fast-forwarded into `release/v0.8.0-…` (or whatever the new branch name will be)
- [ ] Old `release/v0.7.0-installer-3-options` branch left alone for archive

## Long-term maintenance checklist

These come back to bite you 6-18 months out if ignored.

- [ ] Quarterly: run `pyright app/ core/` + the full test suite on the head of the active branch. Catches drift.
- [ ] Each new feature: add to CHANGELOG.md in the same commit.
- [ ] Each new module: add to BOTH `whisper_project_*.spec` files' hidden imports.
- [ ] Each release: re-test the install/uninstall flow once before tagging.
- [ ] Each year: re-read `SENIOR_REVIEW_2026-05-21.md` + `EXECUTION_ROADMAP.md`. Items that survive two annual reviews are real technical debt; budget time to fix.
- [ ] Each Whisper / faster-whisper minor release: re-run the smoke tests + spot-check on a non-English clip.
- [ ] Each Python minor release: confirm `pyproject.toml` upper bound + `tested on Python X.Y` note in requirements.txt.
- [ ] Each PyInstaller minor release: rebuild + verify the size + first-launch wizard.

---

## Recommendation

**Do not freeze today.** Do this in two sessions:

### Session A — close the small gaps (~2 hours)
- R-1 (flaky test): 30 min
- R-3 (safe_thread migration): 1 hour
- R-5 (--safe-mode flag): 30 min
- R-8 (RELEASE_PROCESS.md): 45 min

That gets the safe-for-private-distro state. Total: ~3 hours.

### Session B — build + validate (~half a day)
- R-2 (full except sweep): 2-3 hours
- R-6 + R-7 (build + manual test): half a day
- R-4 (crash-resume test): half a day

After Session B, the branch is ready to freeze.

Optionally Session C: polish opportunities P-1 through P-4. Skip
unless you want the docs to feel finished.

---

*End of freeze audit.*
