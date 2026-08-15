# Code review — v1.7.0 commits (second pass, adversarial angle)

Scope: `git range 6aa0ac5..3122296` (the 12 commits authored this
session that shipped as v1.7.0). Run via the `code-review` skill at
`high` effort, as a follow-up to an earlier manual review pass of the
same range. Both findings below were independently verified (not just
raised) before being reported.

## Findings

### 1. `core/backends/google_cloud_stt.py:157` — GC-disable race across modules

The GC-mid-import crash mitigation (ADR 0008) uses a separate
`threading.Lock()` **per module** (`core/alignment.py`,
`core/backends/availability.py`, `core/backends/google_cloud_stt.py`,
`core/backends/whisper_cpp.py`, `core/diarization.py`,
`core/hardware.py`, `core/llm.py`, `core/search.py`,
`core/separator.py`, `core/voiceprint.py`) — 10 distinct locks. But
`gc.disable()` / `gc.enable()` are **process-global**, not
thread-local or lock-scoped. Two of these guarded call sites running
concurrently on different daemon threads (different locks, so neither
blocks the other) are not serialized against each other at all.

**Failure scenario:** user changes the engine dropdown (spawns
`app.app._probe` calling e.g. `core/backends/whisper_cpp.py`'s
`is_available()`) while the Hardware Wizard's re-probe is also in
flight (`core/hardware.py`'s `probe_tiers()`, a different lock). Both
threads see GC enabled and call `gc.disable()`. Whichever import
finishes first hits `finally: if was_enabled: gc.enable()` and turns
GC back on **process-wide** while the other thread's heavy
C-extension import is still mid-construction — reproducing the exact
`STATUS_BREAKPOINT` native fault ADR 0008 was written to fix. ADR 0008
itself already documented 3 concurrent `_probe` threads racing in
practice, confirming this kind of concurrency is realistic in this
app; the fix just didn't account for two *differently-locked* call
sites undoing each other's protection.

### 2. `core/alignment.py:44` — the guard is duplicated 10x instead of shared

The same ~15-line lock + `gc.disable()`/`gc.enable()` import guard is
copy-pasted verbatim across all 10 files above instead of being
factored into one shared helper backed by one shared, process-wide
lock. This is both a maintainability problem and the direct root
cause of finding 1 — a shared lock would make the mitigation correct
under concurrency for free.

**Failure scenario:** a future contributor adds an 11th heavy-import
call site and copies the same per-module-lock pattern (as this diff
itself did 9 times), perpetuating the race instead of fixing it once.

### 3. `docs/CHANGELOG.md:48` (and ~71, ~82) — entries violate this repo's own changelog rule

`CLAUDE.md` states verbatim: *"`docs/CHANGELOG.md` bullets must stay
skimmable: 1–3 sentences — what broke/changed + the fix, not a
root-cause narrative. The full investigation ... belongs in the
commit message and/or `docs/SESSION_HANDOFF_NEXT.md`, never in the
changelog itself."*

The new `[1.7.0]` bullet "Engine-status / hardware-probe background
threads hardened..." runs 5 sentences and narrates the
`STATUS_BREAKPOINT` crash, "four rounds of instrumented
full-test-suite reproduction," and points to ADR 0008 for "the full,
honest multi-round story" — exactly the investigation content the
rule reserves elsewhere. Two nearby bullets have the same
root-cause-narrative shape.

## Disposition

- Findings 1+2: fix together — introduce one shared, process-wide
  lock + a small reusable guard, replace all 10 per-module copies.
- Finding 3: trim the CHANGELOG.md entries to 1-3 sentences each,
  per the project's own rule (detail already lives in
  `docs/SESSION_HANDOFF_NEXT.md` and the commit messages).
