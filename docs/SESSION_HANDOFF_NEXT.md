# Next session — read THIS FIRST

Single-source-of-truth handoff for the next development session on
this repo. Read this file before anything else.

---

## 1. Current state (2026-05-25)

| Item | Value |
|---|---|
| Branch | `chore/cleanup-hardening` — carries **v1.3.0** (all committed + pushed) |
| Version | pyproject = 1.3.0; `core.__version__` = 1.3.0; both `.iss` = 1.3.0 |
| Last PUBLISHED release | **v1.3.0** on GitHub — built + smoke-tested (installed tree) + published 2026-05-25 |
| GitHub releases now | `v1.3.0` (latest) + `basic-v0.1.0`; v1.2.0 + earlier releases/tags were pruned |
| Installed test copy | `C:\Temp\wp_v130_test` (silent-installed v1.3.0, KEPT for the user — do NOT delete). Launch: `C:\Temp\wp_v130_test\python\pythonw.exe C:\Temp\wp_v130_test\gui.py`. (The older `C:\Temp\wp_v120_test` may still exist.) |
| Default GitHub branch | `master` (untouched) |
| Working tree | clean (only `.claude/` untracked) |
| Gate | `run_tests.bat` → pyright 0/0/0 (app/ + core/) + hermetic suite — last run **ALL GREEN** |
| Build prereqs (this PC) | Inno Setup `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` ✓ · test video `E:\3029-NWN-Daily-Scroll-2m_0002.mp4` ✓ · extracted model under `%LOCALAPPDATA%\WhisperProject` ✓ |
| Version source of truth | `core/__init__.py` `__version__` (bundled; About dialog + telemetry read it). Bump it with pyproject + both `.iss` every release. |

### What shipped in v1.3.0 (PUBLISHED 2026-05-25)

UX + reliability on top of v1.2.0. Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.3.0.md`. Headlines: **fixed auto-transcribe after
a merged video+audio download** (the saved-path parser matched the
yt-dlp-deleted audio fragment, so Shorts / reels silently failed to
transcribe — now `select_saved_path` makes the merged file win); per-row
**graphical progress bars** in both queues (`progress_cell`); the
**version is now visible** (window title `_base_title` + a version-stamped
installer shortcut via a `#define MyAppVersion` knob); the **Download row
shows "transcribing" + live progress** after an auto-transcribe (linked
via `TranscriptionTask.source_download` ↔
`VideoDownloadTask.transcription_task`, flipped back in `finish_task`);
the **"Last result" card** no longer expands to fill the Transcribe tab;
and the **language picker resets to "Auto" every launch** (no longer
persisted; other prefs still are).

### What shipped in v1.2.0 (published 2026-05-25, now pruned from GitHub)

UX + accessibility on top of v1.1.0. Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.2.0.md`. Headlines: app-wide copy/paste fix
(layout-independent Ctrl+C/V/X/A + right-click menus on every text field
+ a copyable log console), bulk multi-select queue actions (cancel /
re-run / resume / remove), auto-hiding queue scrollbars, model
download-status + a "Download now" button, "Open file" for finished
downloads, output-file de-dup (`name (1).srt`), the About dialog showing
the live version, and a stable installer `AppId` (single Add/Remove
entry that upgrades cleanly).

### v1.1.0 changes (folded into the published v1.2.0; v1.1.0 itself pruned)

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

## 3. v1.3.0 RELEASE — DONE (2026-05-25). Only GUI-manual checks remain.

The full pipeline ran green and v1.3.0 is live on GitHub. The installed
copy at `C:\Temp\wp_v130_test` is KEPT for the user to test — do NOT
uninstall/delete it. For reference, the steps (all COMPLETE) were:

1. ✅ embed rebuild (`build_embed_installer.bat`) — "embed_import_ok" /
   "build complete".
2. ✅ Installer compiled — the new `#define MyAppVersion` + version-stamped
   shortcut compiled clean (569 s) →
   `dist_installer\WhisperProject-v1.3.0-Setup-Standard.exe` (~349 MB).
3. ✅ Smoke E2E on the built tree AND the installed tree — both
   `2 passed, 1 skipped` (real transcription works on v1.3.0).
4. ✅ Silent-installed to `C:\Temp\wp_v130_test` and KEPT. Launch:
   `C:\Temp\wp_v130_test\python\pythonw.exe C:\Temp\wp_v130_test\gui.py`
   (or Start-menu → "Whisper Project 1.3.0").
5. ✅ Published — tag `v1.3.0` pushed + `gh release create` with the
   Setup-Standard EXE + `docs/RELEASE_NOTES_v1.3.0.md`.
6. ✅ Pruned v1.2.0 (`gh release delete v1.2.0 --cleanup-tag --yes`) —
   GitHub now has only `v1.3.0` + `basic-v0.1.0` (archive tags kept).
7. **GUI-manual checks the user will do** (not automatable): the per-row
   progress bars in both queues, the version in the title bar / shortcut,
   the Download row reading "transcribing" with live progress after an
   auto-transcribe (try a YouTube Short / reel with "Transcribe after
   download" on), the smaller "Last result" card, and the language picker
   starting at "Auto".

**To cut the NEXT release** (vX.Y.Z), bump the version in
`core/__init__.py` + `pyproject.toml` + both `.iss` files (the embed
`.iss` reads `#define MyAppVersion`), then repeat steps 1–6. Use absolute
paths via `cmd.exe` (a background cmd may not inherit cwd); `<REPO>` =
`C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2`.
Full step-by-step lives in `docs/RELEASE_PROCESS.md`.

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
