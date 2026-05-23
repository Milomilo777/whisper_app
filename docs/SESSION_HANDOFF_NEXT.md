# Next session — read THIS FIRST

Single-source-of-truth handoff for the next development session on
this repo. Read this file before anything else.

---

## 1. Current state (2026-05-23)

| Item | Value |
|---|---|
| Branch | `chore/cleanup-hardening` (carries v1.0.2; pushed to origin) |
| Last commit | `3632eaf` — release: bump to v1.0.2 |
| Default GitHub branch | `master` (untouched) — separate from this branch |
| Release tag | `v1.0.2` on GitHub with two EXEs uploaded |
| Archive tag | `archive/release-v0.7-baseline` — pre-orphan snapshot |
| Working tree | clean |
| Unit suite | 551 passing |
| Real-file E2E | 10/10 PASS (`tests/core/test_v08_real_file_e2e.py`) |
| Pyright basic | 0 errors, 0 warnings, 0 informations |
| Smoke + end-to-end | 7/7 PASS against real SMTV clip |

## 2. Two deliverables

Both live on GitHub as assets of the v1.0.2 release. The Compact
installer pipeline still exists in the repo and still builds, but
is intentionally not shipped — Portable + Standard cover every
audience.

| Asset | Local path | Size |
|---|---|---|
| Portable | `dist/WhisperProject-v1.0.2-Portable.exe` | 447 MB |
| Setup-Standard | `dist_installer/WhisperProject-v1.0.2-Setup-Standard.exe` | 349 MB |

Download from:
**[github.com/Milomilo777/whisper-project/releases/latest](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)**

### What's in v1.0.2

Reliability + UX release on top of v1.0.1. Two themes:
**resume-from-cancellation** (a 3-hour file cancelled at 47 %
picks up where it left off, not at zero) and the **multi-day
uptime stability sweep** (every silent C call wrapped, off-thread
Tk routed through a queue, per-folder config leak closed, Demucs
temp leak fixed). See `docs/RELEASE_NOTES_v1.0.2.md` for the full
list.

## 3. What's pending

- Manual install testing on a fresh Windows user profile (see
  `docs/RELEASE_PROCESS.md` Step 6). The code is end-to-end tested;
  the manual pass exists to verify the installer GUI flow and the
  first-run Hub Folder dialog on a real clean install.
- Audit follow-ups: every P1 in `docs/STABILITY_AUDIT_2026-05-23.md`
  is still open. P0-4 / P0-5 (LLM-titling silence) were
  deliberately deferred — they need a slightly bigger plumbing
  change than the tonight pass allowed.

## 4. Branch + tag map

```
origin/master                       (historical, untouched)
origin/chore/cleanup-hardening      ← v1.0.2 lives here
  tag v1.0.2                        ← the release commit (3632eaf)
  tag archive/release-v0.7-baseline ← pre-orphan snapshot (recovery aid)
  tag v0.7.1, v0.7.0                ← historical releases
```

The `chore/cleanup-hardening` branch is an **orphan** — its git
history begins with a single squashed commit (no parents). The
full prior history is preserved at `master` + the archive tag,
never lost.

## 5. The 1-line restart prompt

```
Read docs/SESSION_HANDOFF_NEXT.md first, then continue on the chore/cleanup-hardening branch. Don't touch master. Don't force-push (v1.0.2 is public).
```

## 6. Forbidden actions (durable; mirrors CLAUDE.md)

- Don't merge to master
- Don't checkout master
- Don't push to master
- Don't touch `.git/config`
- Don't code-sign the EXE
- Don't `git push --force` (v1.0.2 is public; force-pushing would
  invalidate the user's downloaded artefacts)

## 7. Sanity-check commands for the next session

```cmd
cd C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2
git log --oneline -5
git status
pyright app/ core/
python -m pytest tests/ --ignore=tests/smoke
```

Expected: 551 tests pass, pyright 0/0/0, working tree clean.

## 8. Key documents

| Doc | Purpose |
|---|---|
| [README.md](../README.md) | Project overview + install + config |
| [docs/INSTALL.md](INSTALL.md) | End-user install steps |
| [docs/BUILD.md](BUILD.md) | Two shipped build pipelines + the unshipped Compact one |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | Process model + threading |
| [docs/CONFIG.md](CONFIG.md) | Every config key documented |
| [docs/RELEASE_PROCESS.md](RELEASE_PROCESS.md) | How to ship the next release |
| [docs/RELEASE_NOTES_v1.0.2.md](RELEASE_NOTES_v1.0.2.md) | v1.0.2 user-facing notes |
| [docs/CHANGELOG.md](CHANGELOG.md) | Full version history |
| [docs/STABILITY_AUDIT_2026-05-23.md](STABILITY_AUDIT_2026-05-23.md) | Multi-day stability audit + the P1 punch list |
| [CLAUDE.md](../CLAUDE.md) | Durable rules for any Claude Code session |
