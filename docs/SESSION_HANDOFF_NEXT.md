# Next session — read THIS FIRST

Single-source-of-truth handoff for the next development session on
this repo. Read this file before anything else.

---

## 1. Current state (2026-05-23)

| Item | Value |
|---|---|
| Branch | `chore/cleanup-hardening` (carries v1.0.1; pushed to origin) |
| Last commit | `c110a27` — release: bump to v1.0.1 |
| Default GitHub branch | `master` (untouched) — separate from this branch |
| Release tag | `v1.0.1` on GitHub with all three EXEs uploaded |
| Archive tag | `archive/release-v0.7-baseline` — pre-orphan snapshot |
| Working tree | clean |
| Unit suite | 535 passing |
| Real-file E2E | 10/10 PASS (`tests/core/test_v08_real_file_e2e.py`) |
| Pyright basic | 0 errors, 0 warnings, 0 informations |
| Smoke + end-to-end | 7/7 PASS against real SMTV clip |

## 2. Three deliverables

All three live on GitHub as assets of the v1.0.1 release:

| Asset | Local path | Size |
|---|---|---|
| Portable | `dist/WhisperProject-v1.0.1-Portable.exe` | 447 MB |
| Setup-Compact | `dist_installer/WhisperProject-v1.0.1-Setup-Compact.exe` | 326 MB |
| Setup-Standard | `dist_installer/WhisperProject-v1.0.1-Setup-Standard.exe` | 349 MB |

Download from:
**[github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)**

### What's in v1.0.1

First stable release. Full feature set, multi-round hardening,
and a same-day fix for a fresh-install model re-download race:
the worker used to spawn before the user clicked OK on the
first-run hub picker, downloading the model to a path the next
launch wouldn't look at — triggering a full 3 GB re-download.
See `docs/RELEASE_NOTES_v1.0.1.md` and commits `c419b6e` +
`c110a27`.

## 3. What's pending

Only a single class of work remains: **manual install testing on a
fresh Windows user profile.** See `docs/RELEASE_PROCESS.md` Step 6.
The code is end-to-end tested; the manual pass exists to verify the
installer GUI flow and the first-run Hub Folder dialog on a real
clean install.

## 4. Branch + tag map

```
origin/master                       (historical, untouched)
origin/chore/cleanup-hardening      ← v1.0.1 lives here
  tag v1.0.1                        ← the release commit (c110a27)
  tag archive/release-v0.7-baseline ← pre-orphan snapshot (recovery aid)
  tag v0.7.1, v0.7.0                ← historical releases
```

The `chore/cleanup-hardening` branch is an **orphan** — its git
history begins with a single squashed commit (no parents). The full
prior history is preserved at `master` + the archive tag, never lost.

## 5. The 1-line restart prompt

```
Read docs/SESSION_HANDOFF_NEXT.md first, then continue on the chore/cleanup-hardening branch. Don't touch master. Don't force-push (v1.0.1 is public).
```

## 6. Forbidden actions (durable; mirrors CLAUDE.md)

- Don't merge to master
- Don't checkout master
- Don't push to master
- Don't touch `.git/config`
- Don't code-sign the EXE
- Don't `git push --force` (v1.0.1 is public; force-pushing would
  invalidate the user's downloaded artefacts)

## 7. Sanity-check commands for the next session

```cmd
cd C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2
git log --oneline -5
git status
pyright app/ core/
python -m pytest tests/ --ignore=tests/smoke
```

Expected: 534 tests pass, pyright 0/0, working tree clean.

## 8. Key documents

| Doc | Purpose |
|---|---|
| [README.md](../README.md) | Project overview + install + config |
| [docs/INSTALL.md](INSTALL.md) | End-user install steps |
| [docs/BUILD.md](BUILD.md) | Three build pipelines |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | Process model + threading |
| [docs/CONFIG.md](CONFIG.md) | Every config key documented |
| [docs/RELEASE_PROCESS.md](RELEASE_PROCESS.md) | How to ship the next release |
| [docs/RELEASE_NOTES_v1.0.1.md](RELEASE_NOTES_v1.0.1.md) | v1.0.1 user-facing notes |
| [docs/CHANGELOG.md](CHANGELOG.md) | Full version history |
| [CLAUDE.md](../CLAUDE.md) | Durable rules for any Claude Code session |
