# Execution Roadmap — derived from the 2026-05-21 senior review

This document converts the audit in `SENIOR_REVIEW_2026-05-21.md`
into an **executable plan**. Every task here is small enough to ship
in one focused patch, with a clear validation step.

The roadmap consciously **drops** the LICENSE-related items from the
audit. Per the owner's direction this project is being distributed
privately to a small group of users, not to the public internet, so
public-release legal hygiene is not a blocker.

---

## How to read this roadmap

Every item has six attributes:

| Attribute | Meaning |
|---|---|
| **ID** | Stable shortcode, used in branch + commit names |
| **Complexity** | XS / S / M / L / XL — rough engineering size |
| **Risk** | how easy is it to break something unrelated |
| **Order** | suggested place in the queue (1 = do first) |
| **Impact** | what gets better |
| **Regression risk** | concrete failure mode if the fix goes wrong |

Tasks are also tagged with one of six **buckets** that drive
sequencing:

1. **Quick wins** — XS/S, low-risk, immediate value. Do first.
2. **Medium refactors** — M, contained scope, manageable risk. Do second.
3. **Dangerous areas** — touches threading, IPC, subprocess, atomic
   writes. Must be done with extra discipline (own branch, real-file
   E2E run, careful review).
4. **Freeze blockers** — must be true before we stop changing code for
   the v0.8 release window.
5. **Release blockers** — must be true before users get a new build.
6. **Long-term improvements** — valuable but not blocking; come back to
   after the freeze.

---

## 1 · Quick wins

Patches small enough that landing each one in a single commit on a
short-lived branch is overkill.

| ID | Task | Cx | Risk | Order | Impact | Regression risk |
|---|---|---|---|---|---|---|
| QW-01 | Add `LICENSE`-less `NOTICE.md` covering bundled binaries (ffmpeg, yt-dlp) — keep upstream attributions explicit even for private distro | XS | None | 1 | Defensible re-distribution to private users | None |
| QW-02 | Sweep `requirements.txt` historical commentary | XS | None | done | Scannable manifest | None ✅ done in Batch 0 |
| QW-03 | Add `docs/README.md` navigation index | XS | None | done | New contributors find docs faster | None ✅ done in Batch 0 |
| QW-04 | Delete `docs/HANDOFF_NEXT_SESSION.md` duplicate | XS | None | done | One source of truth | None ✅ done in Batch 0 |
| QW-05 | Move V08/V09 research into `docs/roadmap/` | XS | None | done | Current state vs. future planning is now visible at a glance | None ✅ done in Batch 0 |
| QW-06 | Bump `pyproject.toml` version to reflect shipped v0.8 work (`0.7.1` → `0.8.0-dev` on this branch) | XS | Low | 2 | Audit / debug clarity. `app/observability.py` reports the right version. | One pyright type-narrow on the version literal — none in this codebase. |
| QW-07 | Add `logger.info` at every device / backend / model decision point (B5) | S | Low | 3 | Support requests gain a paper trail | None — additive logs only |
| QW-08 | Raise `RuntimeError` when `_write_outputs` writes zero files (A5) | XS | Low | 4 | Disk-full silently turning into "Done in 0.02s" stops happening | A degenerate empty-formats case might surface as a hard error; mitigated by guarding on `if formats and not written`. |
| QW-09 | Daemon thread wrapper that logs unhandled exceptions (B3) — additive helper only; no call-site migration in this patch | S | None | 5 | New code can adopt safer threading pattern from day 1 | None — purely additive |
| QW-10 | Add `logger.exception()` to the three highest-traffic except blocks: `load_model_async`, `_burn_subs_for`, `tray_loop` (B3 partial) | S | Low | 6 | Stack traces appear in the log for the three places that have historically swallowed exceptions silently | None — error path was already broken, we just log it |
| QW-11 | Add `PRAGMA journal_mode = WAL` to history DB open (D2) | XS | Low | 7 | Crash-safety for `history.db` | First open after the change rewrites the journal; aborted upgrade can leave a `.wal` + `.shm` sidecar. Document. |
| QW-12 | Add per-task `[task=… file=…]` prefix to transcribe-loop logs (B6) | S | Low | 8 | Parallel-worker logs become readable | None — purely cosmetic, no parser depends on the current format |
| QW-13 | Log the fallback chain when `model_path` is recomputed (B11) | XS | Low | 9 | "Why is the model loading from a weird path?" becomes self-explaining | None |

---

## 2 · Medium refactors

These move code but don't change behaviour. Each fits in one branch.

| ID | Task | Cx | Risk | Order | Impact | Regression risk |
|---|---|---|---|---|---|---|
| MR-01 | Move build artefacts (`*.bat`, `*.iss`, `whisper_project_*.spec`) into `packaging/` | M | Med | 10 | Repo root looks like a project, not a workspace | All build commands must be updated; broken build = broken release. Validate by running both `build.bat` flows locally before pushing. |
| MR-02 | Centralise device detection in `core/hardware.py` and delete the duplicate in `core/backends/faster_whisper_be.py` (A7) | M | Low | 11 | One place to fix CUDA quirks | Existing tests cover both call sites; run full test suite + smoke. |
| MR-03 | Extract `_prepare_runtime_config()`, `_dispatch_backend()`, `_write_artefacts()` from `transcribe()` (A6) | L | Med | 12 | `transcribe()` becomes testable in isolation | High — every helper must keep the exact same call signature into post-pipeline. Cover with the existing 437-test suite + real-file E2E. |
| MR-04 | Replace `task.paused` + `task.cancelled` bools with one `TaskState` enum + guarded transitions (A14) | M | Med | 13 | Pause-then-cancel becomes deterministic | Two backends (faster_whisper + parakeet) consume the flags; both must be updated together. |
| MR-05 | Schema-validate `.whisperproject.json` overrides on load (A11) | M | Low | 14 | Bad overrides surface as a warning, not a downstream type error | The validator must be exhaustive; missing keys are silently skipped today. |
| MR-06 | Centralise retry helper `with_retries(fn, attempts, backoff)` and apply to: model download, LLM download, telemetry post (B9) | M | Low | 15 | Consistent flaky-network behaviour | None — each call site preserves its current attempt count when migrated |
| MR-07 | Cap event queues with `maxsize=1000`, drop-oldest policy on full (A13) | S | Low | 16 | Memory bound under event storms | Slow consumers may lose progress events but that's the intended trade-off; document. |

---

## 3 · Dangerous areas (extra care)

Threading, IPC, subprocess, atomic writes. Each requires its own
branch, its own real-file E2E run, and explicit pre-merge validation.

| ID | Task | Cx | Risk | Order | Impact | Regression risk |
|---|---|---|---|---|---|---|
| DZ-01 | Move worker `stdin` writes off the Tk thread to a dedicated writer thread with per-command timeout (A1) | L | **High** | 17 | UI never freezes on full stdin pipe | A timeout that's too short cancels in-flight jobs. Start with 30 s. |
| DZ-02 | Insert history-DB row BEFORE worker dispatch (A3) | M | Med | 18 | Tasks always have a history trail | If insert fails the dispatch must not happen — could mask a transient DB lock as "task never started". |
| DZ-03 | Add per-worker UUID session token, route events by token instead of PID (A4) | M | Med | 19 | Stale-event misrouting after worker restart goes away | Both producer + consumer must roll out together; old-format events become unroutable. Need a backwards-compat window. |
| DZ-04 | Worker heartbeat — emit every 5 s; parent declares dead at 30 s (D8) | M | Med | 20 | Crashed worker no longer leaves "running" task forever | Slow CPU systems may spuriously hit the timeout under load; need a generous window + opt-out. |
| DZ-05 | Encapsulate transcriber module-level globals in a session class (A2) | L | Med | 21 | Future in-process worker pools can't trample each other | Tests monkeypatch the globals heavily; the shim layer must keep the names alive long enough to migrate tests. |
| DZ-06 | Atomic read-modify-write for `config.json` (D1) | M | Med | 22 | Hand-edits + program-writes stop racing | Validate by running 50 parallel saves in a test. |

---

## 4 · Freeze blockers

Before the v0.8 code freeze, all of these must be in place. They're
not features — they're "we trust this version" gates.

| ID | Task | Cx | Risk | Order | Impact |
|---|---|---|---|---|---|
| FB-01 | Sweep every `except` block: every one logs with context (B1) | M | Low | 23 | Silent-failure rate drops dramatically |
| FB-02 | Sweep every `logger.warning("…: %s", e)` → `logger.exception("…")` inside `except` blocks (B2) | S | Low | 24 | Stack traces appear in logs |
| FB-03 | Daemon-thread migration: move ALL `threading.Thread(...)` calls in app/+core/ to the wrapper from QW-09 | M | Low | 25 | Every background crash is logged |
| FB-04 | Add integration test for crash-mid-transcribe → restart → resume produces a valid output (B12) | M | Low | 26 | Crash recovery is provably correct |
| FB-05 | Add `--safe-mode` CLI flag (D10) | S | Low | 27 | Broken config / hub never blocks startup |
| FB-06 | Run pyright in CI on every PR | XS | Low | 28 | Type-clean baseline doesn't drift |
| FB-07 | Add CHANGELOG.md gate in CI (every PR touches it unless labelled `no-changelog`) | XS | Low | 29 | Release notes stay current |
| FB-08 | Document the freeze + release process in `docs/RELEASE_PROCESS.md` | S | None | 30 | Anyone can ship a release |

---

## 5 · Release blockers

Before a build is uploaded to the private user group, these must be
satisfied. (LICENSE explicitly dropped per owner direction.)

| ID | Task |
|---|---|
| RB-01 | All freeze-blockers complete |
| RB-02 | `BUILD.md` updated for the version being released (size, output path) |
| RB-03 | `RELEASE_NOTES_v0.X.md` written |
| RB-04 | Three deliverables actually built locally: Portable EXE, Setup-Compact, Setup-Standard |
| RB-05 | Each deliverable smoke-tested on a fresh user profile (delete `%LOCALAPPDATA%\WhisperProject` between runs) |
| RB-06 | Full unit suite + real-file E2E + smoke green on the release commit |
| RB-07 | Inno Setup compile succeeds for both `.iss` files |
| RB-08 | First-run hub-folder dialog tested end-to-end on a fresh user profile |
| RB-09 | Uninstaller tested for both "hub inside {app}" and "hub on D:\" cases |
| RB-10 | `pyproject.toml` version bumped + tag pushed |

---

## 6 · Long-term improvements

Pick these up after the freeze. They're net-good but not blocking.

| ID | Task |
|---|---|
| LT-01 | Switch model integrity check from MD5 → SHA-256 |
| LT-02 | Stream segments to disk for files > 60 min (memory cap) |
| LT-03 | Add corruption check (`PRAGMA integrity_check`) at history.db open |
| LT-04 | Add screenshot to README (was C12) |
| LT-05 | Add troubleshooting / FAQ doc (E4) |
| LT-06 | Add `tests/README.md` describing the test taxonomy (E6) |
| LT-07 | Add architecture sequence diagram (E8) |
| LT-08 | Add a sample audio + expected JSON in `examples/` (E9) |
| LT-09 | Move OpenVINO probe Windows-only gate (A16) |
| LT-10 | Standardise burn-subs path escape per OS (A15) |

---

## Branching strategy

* **One branch per batch**, even when the batch is XS.
  Naming: `chore/qw-01-notice-md`, `chore/qw-07-decision-logs`, etc.
* Branch base: latest `chore/cleanup-hardening` (the integration branch
  this roadmap was committed on). When the integration branch reaches a
  good resting state, promote it back to the release branch by fast-
  forward merge.
* No `master` operations. The owner's CLAUDE.md is explicit about this.
* Push the per-batch branch only when **its** validation is green.
  Don't carry uncommitted work across batches.

## Testing strategy

Every batch lands with one of three test profiles:

| Test profile | When |
|---|---|
| **Tier A — unit only** | XS / S patches that touch ≤ 3 files and add no IO. `pytest tests/ --ignore=tests/smoke --ignore=tests/core/test_v08_real_file_e2e.py`. Must be 100 % green. |
| **Tier B — unit + real-file E2E** | M patches, or anything that touches `core/transcriber.py`, writers, or the worker. Add `tests/core/test_v08_real_file_e2e.py`. ~3 min. |
| **Tier C — unit + E2E + smoke + manual installer** | L+ patches in dangerous areas, OR release commits. Adds `tests/core/test_transcribe_smoke.py`, `tests/core/test_transcribe_end_to_end.py`, plus a manual install + uninstall pass. |

`pyright app/ core/` runs in every tier. Must be 0 errors, 0 warnings.

## Freeze checklist

Run from top to bottom; nothing skipped.

- [ ] All FB-* tasks merged into the integration branch
- [ ] `pyright app/ core/` → 0 errors, 0 warnings
- [ ] `pytest tests/ --ignore=tests/smoke` → all green
- [ ] Real-file E2E (10/10 tests in `test_v08_real_file_e2e.py`) → green on a freshly-cloned profile
- [ ] Smoke + end-to-end → green
- [ ] Manual: launch the app from `gui.py`. First-run hub dialog appears. Pick a folder. Confirm config.json was written.
- [ ] Manual: rename `%LOCALAPPDATA%\WhisperProject\config.json`. Relaunch. Confirm clean recovery + fresh first-run dialog.
- [ ] CHANGELOG.md has an entry for every commit since the last release
- [ ] `pyproject.toml` version bumped
- [ ] `docs/SESSION_HANDOFF_NEXT.md` updated with the freeze state

## Release readiness checklist

Run after the freeze checklist + before pushing the release tag.

- [ ] `build.bat` (or successor) produces a clean Portable EXE
- [ ] `build_embed_installer.bat` produces a clean embed tree
- [ ] `ISCC.exe installer.iss` produces `WhisperProject-vX.Y.Z-Setup-Compact.exe`
- [ ] `ISCC.exe installer_embed.iss` produces `WhisperProject-vX.Y.Z-Setup-Standard.exe`
- [ ] Install each of the three deliverables on a fresh test profile.
      Transcribe one short file. Confirm output written. Uninstall.
- [ ] Uninstall test — hub INSIDE `{app}`: hub goes away with install.
- [ ] Uninstall test — hub OUTSIDE `{app}`: user is prompted. Answer No → hub stays. Answer Yes → hub deleted.
- [ ] All three exe outputs uploaded to release page
- [ ] Release notes (`RELEASE_NOTES_vX.Y.Z.md`) attached as the release body
- [ ] Tag pushed (`vX.Y.Z`)
- [ ] Old `release/...` branch deleted or archived

---

## Recommended execution sequence

The order below is the safe path. Each step is small enough to revert
in one git command if the validation fails.

1. **Quick wins QW-06 → QW-13** in order, one commit each. ~½ day total.
2. **Medium refactors MR-01 (packaging move)** alone — touches every
   build script. Validate by running both build flows locally.
3. **MR-02 (centralise device detection)** + **MR-06 (retry helper)** —
   neither touches the worker IPC. Safe pair.
4. **MR-03 (`transcribe()` split)** alone, with extra care. Run real-file
   E2E + smoke before pushing.
5. **MR-04 + MR-05 + MR-07** — three small refactors that compose well.
6. **Dangerous zone**, one item at a time, each on its own branch:
   DZ-01 → DZ-02 → DZ-03 → DZ-04 → DZ-05 → DZ-06.
7. **Freeze sweep** FB-01 → FB-08.
8. **Release** per the checklist.

Everything in section 6 (long-term) happens after this whole sequence
ships.

---

*End of roadmap.*
