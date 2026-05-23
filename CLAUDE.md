# Whisper Project — durable instructions for any Claude Code session

This file is auto-loaded into every Claude Code session opened
inside this repository. Read it on first turn; follow it for the
whole session.

## Commit + push cadence — DURABLE RULE

Anything that takes meaningful work to redo MUST be committed
and pushed the moment it lands, not at the end of the session.
"Meaningful" means roughly anything ≥ 30 minutes of focused work,
or any chunk where a power outage / process crash mid-session
would lose user-visible progress.

Concretely:

- **Every coherent feature, fix, or refactor**: as soon as it
  passes pyright + the relevant unit tests, commit it, then
  push it to the current branch.
- **Every docs-only change** that adds non-trivial content
  (>50 lines, or a brand-new doc): commit + push immediately.
- **Every build/spec change**: commit + push before rebuilding
  the deliverables, so if the build crashes mid-way the source-
  of-truth is already on origin.
- **Every batch of test additions**: commit + push.

Do not wait until "the end of the session" to commit. The user
has explicitly stated they want progress preserved against power
loss; that requires a steady commit + push cadence, not a single
final dump.

Atomic-commit hygiene:

- One coherent change per commit, even if that means 6–8 small
  commits in a row.
- Commit messages follow the project's existing style: imperative
  subject ≤ 70 chars, blank line, body explaining the *why*.
- Don't squash commits across logical groups.

When a build is about to start (PyInstaller / Inno Setup):

- Make sure every modified file is either committed or
  deliberately scratch (and noted in CLAUDE.md context as
  "intentionally not committed yet — see <commit X>").

## Permitted operations on this branch

The current working branch is `chore/cleanup-hardening`. It carries
the v1.0.2 release. The following are pre-authorised for all future
hands-off sessions:

  - `git push origin chore/cleanup-hardening`
  - `git tag -a vX.Y.Z …` + `git push origin vX.Y.Z`
  - `gh release create vX.Y.Z dist/*.exe dist_installer/*.exe`
  - `gh release edit vX.Y.Z --notes-file docs/RELEASE_NOTES_vX.Y.Z.md`

The following remain forbidden unless the user explicitly
asks for them in the current session:

  - Any operation on `master` (checkout, merge, push, …)
  - Code-signing the exe
  - Editing `.git/config`
  - `git push --force` against anything (v1.0.2 is already public —
    force-push would invalidate the user's downloaded artefacts)

## Style & scope

  - English-only repository. The branch is being prepared for a
    handover to a separate maintainer; no Persian / Arabic / RTL
    in docs, code comments, or commit messages. The SMTV scraper
    accepts non-English content URLs; that's per-URL capability,
    not a UI claim.
  - Two shipped deliverables (Portable + Setup-Standard) must
    keep building. The Setup-Compact pipeline still exists in the
    repo and the spec is maintained, but Compact is not published.
    Adding a new module = update both `whisper_project_onefile.spec`
    and `whisper_project_onedir.spec` hidden-import lists (so the
    Compact pipeline doesn't bit-rot).
  - Tests live under `tests/`. The hermetic unit suite is
    `tests/` minus `tests/smoke/`. Smoke needs real resources
    (the Whisper model, a test video at
    `E:\3029-NWN-Daily-Scroll-2m_0002.mp4`, a live network for
    SMTV E2E). Skip via env vars when those aren't present.
  - Pyright must report 0 errors on `app/` and `core/` before
    every commit. The v1.0.2 baseline is 0 errors / 0 warnings /
    0 informations — protect it.

## Handoff file

`docs/SESSION_HANDOFF_NEXT.md` is the source of truth for what's
left. Read it on session start, update it at session end.

## The 1-line restart prompt

```
Read docs/SESSION_HANDOFF_NEXT.md first, then continue on the chore/cleanup-hardening branch. Don't touch master. Don't force-push (v1.0.2 is public).
```
