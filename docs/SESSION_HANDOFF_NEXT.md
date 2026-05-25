# Next session — read THIS FIRST

Single-source-of-truth handoff for the next development session on
this repo. Read this file before anything else.

---

## 1. Current state (2026-05-25)

| Item | Value |
|---|---|
| Branch | `chore/cleanup-hardening` — now carries **v1.1.0** (pushed to origin) |
| Version | `pyproject.toml` = 1.1.0; both `.iss` = 1.1.0 |
| Last published release | `v1.0.3` on GitHub — **v1.1.0 is NOT published yet** |
| Default GitHub branch | `master` (untouched) — separate from this branch |
| Archive tag | `archive/release-v0.7-baseline` — pre-orphan snapshot |
| Working tree | clean |
| One-command gate | **`run_tests.bat`** — pyright (app/ + core/) + hermetic unit suite, PASS/FAIL summary |
| Unit suite | full hermetic suite green (was 578; +~30 this session) |
| Pyright basic | 0 errors, 0 warnings, 0 informations on `app/` + `core/` |
| Real download check | audio fix verified on a real YouTube video (selector resolves to 137+140) |

### What changed in v1.1.0 (2026-05-25)

Fixes + one opt-in feature. Full list in `docs/CHANGELOG.md`; the
bug-hunt method + findings are in
`docs/AUDIT_2026-05-25_boundary_bugs.md`. Headlines: audio restored in
video downloads, three main-thread model-load freezes removed
(download / crash-resume / watched-folder), the model-hub and
download-folder choices now stick, the crash-resume prompt no longer
nags, a truncated SMTV download now fails instead of shipping corrupt,
the About dialog no longer shows the repo URL, and a new opt-in
"Cookies from browser" option (Advanced → Downloads) lets login-walled
sites (FB / IG / TikTok stories, age-gated Shorts) download via the
user's browser session.

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

## 3. What's pending

- **Publish v1.1.0 + prune old releases.** The Standard installer
  builds to `dist_installer/WhisperProject-v1.1.0-Setup-Standard.exe`;
  tag `v1.1.0` + `gh release create` with that EXE + notes. The owner
  then asked to delete the older GitHub releases, keeping only the
  latest. (Destructive on public artefacts — show the delete list
  first and confirm.)
- **Manual install + GUI test** on a fresh Windows profile
  (`docs/RELEASE_PROCESS.md` Step 6): installer flow, first-run Hub
  dialog, and the v1.1.0 GUI changes specifically — no freeze after
  "Transcribe after download"; the Advanced dialog scrolls; the new
  "Cookies from browser" dropdown; the About dialog with no repo URL.
- **Deferred bug-audit items** (`docs/AUDIT_2026-05-25_boundary_bugs.md`):
  SMTV cancel-latency on a stalled socket + no-retry; worker-lifecycle
  hardening (pending-load dangle, `startup_error` blast radius);
  download-row "interrupted" stats skew; the hardware-probe stall (async
  attempt reverted — a proper fix needs the construction test made
  async-aware); and the Class C yt-dlp time-range suspicions (keyframe
  snap, sub-second timecode, open-left bound) — these need a real
  yt-dlp + ffprobe verification harness before any code change.
- Older items still open: the P1s in
  `docs/STABILITY_AUDIT_2026-05-23.md`; SMTV server-side time-range
  slicing (known limitation in `docs/integrations/smtv-brief.md`).

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
