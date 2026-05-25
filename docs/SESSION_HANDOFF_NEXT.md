# Next session — read THIS FIRST

Single-source-of-truth handoff for the next development session on
this repo. Read this file before anything else.

---

## 1. Current state (2026-05-25)

| Item | Value |
|---|---|
| Branch | `chore/cleanup-hardening` — carries **v1.2.0** (all committed + pushed) |
| Version | pyproject = 1.2.0; `core.__version__` = 1.2.0; both `.iss` = 1.2.0 |
| Last PUBLISHED release | **v1.1.0** on GitHub — **v1.2.0 is committed but NOT built/published yet** |
| GitHub releases now | `v1.1.0` (latest) + `basic-v0.1.0`; the old v0.6.0–v1.0.3 releases + tags were pruned this session |
| Default GitHub branch | `master` (untouched) |
| Working tree | clean (only `.claude/` untracked) |
| Gate | `run_tests.bat` → pyright 0/0/0 (app/ + core/) + hermetic suite — last run **ALL GREEN** |
| Build prereqs (this PC) | Inno Setup `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` ✓ · test video `E:\3029-NWN-Daily-Scroll-2m_0002.mp4` ✓ · extracted model under `%LOCALAPPDATA%\WhisperProject` ✓ |
| Version source of truth | `core/__init__.py` `__version__` (bundled; About dialog + telemetry read it). Bump it with pyproject + both `.iss` every release. |

### What changed in v1.2.0 (committed, NOT yet built/published)

UX + accessibility on top of v1.1.0. Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.2.0.md`. Headlines: app-wide copy/paste fix
(layout-independent Ctrl+C/V/X/A + right-click menus on every text field
+ a copyable log console), bulk multi-select queue actions (cancel /
re-run / resume / remove), auto-hiding queue scrollbars, model
download-status + a "Download now" button, "Open file" for finished
downloads, output-file de-dup (`name (1).srt`), the About dialog showing
the live version, and a stable installer `AppId` (single Add/Remove
entry that upgrades cleanly).

### v1.1.0 (already PUBLISHED on GitHub)

Audio-in-downloads fix, the main-thread model-load freezes (download /
crash-resume / watched-folder), model-hub + download-folder persistence,
crash-resume nag, truncated-SMTV-download, About repo-URL removal, and
the opt-in "Cookies from browser" feature. Bug-hunt method + findings:
`docs/AUDIT_2026-05-25_boundary_bugs.md`.

## 2. Shipped deliverable — Standard only going forward

v1.0.3 historically shipped **both** Portable and Standard (both are
GitHub assets of that release). **As of 2026-05-24 the policy changed:
future releases publish Setup-Standard only.** Portable now joins the
Compact pipeline as maintained-but-unshipped — both specs stay in the
repo and keep building so they don't bit-rot, but neither produces a
published EXE anymore.

| Asset | Local path | Size | Shipped going forward? |
|---|---|---|---|
| Setup-Standard | `dist_installer/WhisperProject-v1.0.3-Setup-Standard.exe` | 349 MB | yes — the only published deliverable |
| Portable | `dist/WhisperProject-v1.0.3-Portable.exe` | 447 MB | no — v1.0.3 was its last release |

Download from:
**[github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)**

### What's in v1.0.3

Collaborator-driven UX + memory release on top of v1.0.2.

- **Time-range video download** — optional Start / End on the
  Download tab; yt-dlp's `--download-sections` fetches only the
  slice. SMTV URLs aren't sliced this release (clear warning).
- **Lazy Whisper-model load** — no preload on launch. First
  transcribe of a session shows a modal "Loading Whisper
  model…"; subsequent transcribes reuse the alive worker. Idle
  RAM drops by ~2 GB.

See `docs/RELEASE_NOTES_v1.0.3.md` for the full list.

## 3. What's pending — FINISH THE v1.2.0 RELEASE

The v1.2.0 code is committed and the gate is ALL GREEN. The user
approved: build + release + install + real-test (especially the new
features), and **leave the installed app in place so they can test it
too — do NOT uninstall/delete it.** `embed_build/` is already rebuilt
for v1.2.0 (the heavy step is done). Run from the repo root; use
absolute paths via `cmd.exe` (a background cmd may not inherit the cwd).

`<REPO>` = `C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2`

1. **(DONE this session)** embed rebuild —
   `MSYS_NO_PATHCONV=1 cmd.exe /c '<REPO>\build_embed_installer.bat'`
   ended "build complete"/"embed_import_ok". Re-run only if app/ or
   core/ changed since.
2. **Compile installer** (this VERIFIES the new `AppId` syntax — watch
   for a `[Setup]`/Pascal error):
   `MSYS_NO_PATHCONV=1 "/c/Users/Owner/AppData/Local/Programs/Inno Setup 6/ISCC.exe" '<REPO>\installer_embed.iss'`
   → `dist_installer\WhisperProject-v1.2.0-Setup-Standard.exe` (~349 MB).
3. **Smoke E2E** on the built tree (expect `2 passed, 1 skipped`):
   `WHISPER_SMOKE_EXE='<REPO>\embed_build\python\pythonw.exe' WHISPER_SMOKE_GUI='<REPO>\embed_build\gui.py' python -m pytest tests/smoke/test_exe_real_e2e.py -q`
4. **Silent install + smoke the installed tree** (KEEP it):
   `cmd /c '<REPO>\dist_installer\WhisperProject-v1.2.0-Setup-Standard.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=C:\Temp\wp_v120_test'`
   then smoke with `WHISPER_SMOKE_EXE=C:\Temp\wp_v120_test\python\pythonw.exe` + `...\gui.py`.
5. **Publish** (pre-authorised in CLAUDE.md):
   `git tag -a v1.2.0 -m "Release v1.2.0" && git push origin v1.2.0`
   `gh release create v1.2.0 "dist_installer\WhisperProject-v1.2.0-Setup-Standard.exe" --title "v1.2.0 — clipboard/UX + queue features" --notes-file docs/RELEASE_NOTES_v1.2.0.md`
6. **Prune v1.1.0** (owner's standing rule = keep only the latest):
   `gh release delete v1.1.0 --cleanup-tag --yes`
   → GitHub then has only `v1.2.0` + `basic-v0.1.0` (archive tags kept).
7. **GUI-manual checks the user will do** (not automatable): paste/copy
   under a Persian layout, the right-click text menus, the log console
   "Copy all", bulk multi-select queue actions, the queue scrollbar, the
   model "Download now", "Open file" on a download, the About version.

### Deferred bug-audit items (`docs/AUDIT_2026-05-25_boundary_bugs.md`)
- SMTV cancel-latency on a stalled socket + no-retry; a site-layout
  change silently empties the article transcript.
- Worker-lifecycle: `_pending_load_*` dangle if the awaited worker dies;
  `startup_error` tears down ALL workers, not just the failing one.
- Download rows stuck `interrupted` skew `stats()`.
- Hardware-probe stall (async attempt was REVERTED — a real fix needs
  `test_hardware_wizard_constructs_without_crashing` made async-aware).
- **Class C — needs a REAL yt-dlp + ffprobe harness before changing:**
  `--download-sections` keyframe snap (clip starts early), sub-second
  timecode, open-left `*-MM:SS` bound. Do NOT "fix" these blind.
- Older: P1s in `docs/STABILITY_AUDIT_2026-05-23.md`; SMTV server-side
  time-range slicing (limitation in `docs/integrations/smtv-brief.md`).

## 4. Branch + tag map

```
origin/master                       (historical, untouched)
origin/chore/cleanup-hardening      ← v1.0.3 lives here
  tag v1.0.3                        ← the release commit (7295872)
  tag archive/release-v0.7-baseline ← pre-orphan snapshot (recovery aid)
  tag v0.7.1, v0.7.0                ← historical releases
```

The `chore/cleanup-hardening` branch is an **orphan** — its git
history begins with a single squashed commit (no parents). The
full prior history is preserved at `master` + the archive tag,
never lost.

## 5. The 1-line restart prompt

```
Read docs/SESSION_HANDOFF_NEXT.md first, then continue on the chore/cleanup-hardening branch. Don't touch master. Don't force-push (v1.0.3 is public).
```

## 6. Forbidden actions (durable; mirrors CLAUDE.md)

- Don't merge to master
- Don't checkout master
- Don't push to master
- Don't touch `.git/config`
- Don't code-sign the EXE
- Don't `git push --force` (v1.0.3 is public; force-pushing would
  invalidate the user's downloaded artefacts)

## 7. Sanity-check commands for the next session

```cmd
cd C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2
git log --oneline -5
git status
pyright app/ core/
python -m pytest tests/ --ignore=tests/smoke
```

Expected: 578 tests pass, pyright 0/0/0, working tree clean.

## 8. Key documents

| Doc | Purpose |
|---|---|
| [README.md](../README.md) | Project overview + install + config |
| [docs/INSTALL.md](INSTALL.md) | End-user install steps |
| [docs/BUILD.md](BUILD.md) | Two shipped build pipelines + the unshipped Compact one |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | Process model + threading |
| [docs/CONFIG.md](CONFIG.md) | Every config key documented |
| [docs/RELEASE_PROCESS.md](RELEASE_PROCESS.md) | How to ship the next release |
| [docs/RELEASE_NOTES_v1.0.3.md](RELEASE_NOTES_v1.0.3.md) | v1.0.3 user-facing notes |
| [docs/CHANGELOG.md](CHANGELOG.md) | Full version history |
| [docs/STABILITY_AUDIT_2026-05-23.md](STABILITY_AUDIT_2026-05-23.md) | Multi-day stability audit + the P1 punch list |
| [CLAUDE.md](../CLAUDE.md) | Durable rules for any Claude Code session |
