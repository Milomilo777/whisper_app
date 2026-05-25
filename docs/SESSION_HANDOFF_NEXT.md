# Next session — read THIS FIRST

Single-source-of-truth handoff for the next development session on
this repo. Read this file before anything else.

---

## 1. Current state (2026-05-25)

| Item | Value |
|---|---|
| Branch | `chore/cleanup-hardening` — carries **v1.3.2** (all committed + pushed; a collaborator also pushes here — fetch/rebase before pushing) |
| Version | pyproject = 1.3.2; `core.__version__` = 1.3.2; both `.iss` = 1.3.2 |
| Last PUBLISHED release | **v1.3.2** on GitHub — built + smoke-tested (embed E2E `2 passed, 1 skipped`) + #28 clip end-to-end verified; published 2026-05-25. NOTE: the user said "release, don't wait for the install test", so the silent-install + installed-tree smoke were SKIPPED this release. |
| GitHub releases now | `v1.3.2` (latest) + `basic-v0.1.0`; v1.3.1 + earlier releases/tags were pruned |
| Installed test copy | none built for v1.3.2 (skipped per user). The user installs the published EXE themselves. Older `wp_v131_test` / `wp_v130_test` may still exist. |
| Default GitHub branch | `master` (untouched) |
| Working tree | clean (only `.claude/` untracked) |
| Gate | `run_tests.bat` → pyright 0/0/0 (app/ + core/) + hermetic suite — last run **ALL GREEN** |
| Build prereqs (this PC) | Inno Setup `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` ✓ · test video `E:\3029-NWN-Daily-Scroll-2m_0002.mp4` ✓ · extracted model under `%LOCALAPPDATA%\WhisperProject` ✓ |
| Version source of truth | `core/__init__.py` `__version__` (bundled; About dialog + telemetry read it). Bump it with pyproject + both `.iss` every release. |

### What shipped in v1.3.2 (PUBLISHED 2026-05-25)

Security + features, after a second bug-hunt (4 more parallel shards:
concurrency, resource-leaks, hostile-input, security). Full list:
`docs/CHANGELOG.md` + `docs/RELEASE_NOTES_v1.3.2.md`. Headlines:
**SECURITY** — yt-dlp option injection closed (a "-"-prefixed pasted URL
could hit `--exec`; `"--"` end-of-options added in all 3 yt-dlp argv
builders, regression-tested) + zip-slip guard on model-archive extract;
**Transcribe-tab time range** (#28) — clip_timestamps through the worker,
end-to-end verified (transcribed only 120–180s of a 10-min file, original
timeline, progress→100%); **multi-site download error visibility** — the
queue now shows yt-dlp's real ERROR line + a "Cookies from browser" hint
for login-walled sites (Facebook); **ffprobe "N/A"** tolerated;
**progress %% kept visible** during the startup marquee; a contributed
**hub_folder/model_path** fix (collaborator commit 5b59fbc).

### Still pending (next session)
- **#37 worker cancel/pause/checkpoint (MED-HIGH).** cancel()/pause()
  only mutate the parent-side task; the worker subprocess never receives
  a cancel/pause over stdin, so pause() is a no-op on a running worker and
  cancel works only by killing+restarting (the worker-side cancelled
  checkpoint-flush is dead code → the partial checkpoint is lost on
  cancel). Fix: send a real cancel/pause action over stdin, or document
  pause as a no-op. Also `ensure_worker_ready(headless=True)` can deadlock
  if ever called on the Tk main thread.
- **Resource leaks (MED).** Killing a worker orphans its grandchild
  ffmpeg/demucs (no process-group/job-object kill); `partials/` grows
  unbounded (a killed worker leaves the checkpoint JSON + `.slice.wav`; no
  startup sweep; declining crash-resume doesn't delete the JSON);
  HistoryDB connection isn't closed in on_exit; demucs cache unbounded.
- **#38 selector tuning** — the download selector already falls back to a
  combined stream (`/best`) so it isn't YouTube-locked; the real fix
  shipped is the ERROR SURFACING. Once a user retries Dailymotion on
  v1.3.2 and the queue shows the actual error, fix that specific cause
  (don't change the selector blind — risks the proven YouTube path).
- **burn_subs filter escaping (MED, deferred)** — the SRT path injected
  into ffmpeg's `subtitles=` filter escapes only `\` and `:`, not `'[],`;
  a crafted on-disk filename could break out. Needs a burn-subs test
  harness before changing (don't break normal paths).

### What shipped in v1.3.1 (PUBLISHED 2026-05-25, now pruned from GitHub)

Reliability bug-hunt on top of v1.3.0 (traced each UI action through the
code + four parallel audit agents). Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.3.1.md`. Headlines: **non-ASCII filename downloads
now transcribe** — yt-dlp stdout forced to UTF-8 (`_utf8_subprocess_env`)
PLUS a self-healing fallback (`DownloadService._recover_saved_path`) that
finds the real downloaded file if the parsed path is wrong; **language
codes normalized on the DEFAULT path** (`_normalize_language` now in
`_build_transcribe_kwargs`, not just the alt-backend call — fixes "en-US"
and multi-value picker codes like "zh-Hans,zh-CN" crashing the worker);
**VLC found via registry/Program Files** with a clear 64-bit hint
(`_locate_vlc_dir`); **download cancel stops the linked transcription** +
**re-run keeps the time-range**; **optional-dep probes catch OSError**
(diarization/parakeet/whisper_cpp no longer crash the app on a bad native
DLL — VLC bug class); Transcribe **path validation**; demucs via
`sys.executable`. Plus the queue **"working" marquee** animation and the
**0:00:00 time-range defaults**. New tests: test_normalize_language,
test_recover_saved_path, test_transcribe_kwargs, test_progress_cell
(+marquee).

### Still pending (next session)
- **#28 — time-range for the Transcribe tab**: let the user transcribe
  only a slice of a long local file. Recommended approach: faster-whisper
  `clip_timestamps` threaded through `_build_transcribe_kwargs` (the
  central kwargs builder), with the per-segment progress % computed
  relative to the clip bounds (transcriber.py:~1123) so the bar still
  fills 0→100. Add Start/End fields to the Transcribe tab + clip_start/end
  on TranscriptionTask.
- **Minor**: `watched_folder` has no `_drive_is_mounted` deferral like
  download_folder/model_path, so a not-yet-mounted/temp watched folder is
  silently dropped at launch (app/app.py watched-folder branch). Low
  urgency (degrades gracefully, just doesn't watch).

### What shipped in v1.3.0 (published 2026-05-25, now pruned from GitHub)

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

## 3. v1.3.2 RELEASE — DONE (2026-05-25).

v1.3.2 is live on GitHub. The user asked to "release, don't wait for the
install test", so the silent-install + installed-tree smoke were SKIPPED
(the build was still validated — see steps below). Steps that ran:

1. ✅ embed rebuild (`build_embed_installer.bat`) — "embed_import_ok" /
   "build complete".
2. ✅ Installer compiled clean (805 s) →
   `dist_installer\WhisperProject-v1.3.2-Setup-Standard.exe` (~349 MB).
   IMPORTANT: ISCC writes the EXE incrementally — wait for the "Successful
   compile" line / a stable file size before publishing (a mid-write EXE
   looks ~218 MB and would ship corrupt).
3. ✅ Smoke E2E on the embed tree — `2 passed, 1 skipped`. Plus an
   end-to-end #28 clip check (transcribed only 120–180s of a 10-min file;
   segments on the original timeline; progress reached 100%).
4. ⏭️ Silent-install + installed-tree smoke — SKIPPED (per user).
5. ✅ Published — tag `v1.3.2` + `gh release create` with the
   Setup-Standard EXE + `docs/RELEASE_NOTES_v1.3.2.md`.
6. ✅ Pruned v1.3.1 (`gh release delete v1.3.1 --cleanup-tag --yes`) —
   GitHub now has only `v1.3.2` + `basic-v0.1.0` (archive tags kept).
7. **GUI-manual checks for the user** (not automatable): the Transcribe
   tab time-range (transcribe a slice of a long file); a download from a
   non-YouTube site (the queue now shows the REAL error if it fails — feed
   that error back for a precise fix); a login site (Facebook) → the
   cookie hint; the progress %% visible during start-up; special-char /
   non-English titles transcribing (the v1.3.1 fixes).

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
