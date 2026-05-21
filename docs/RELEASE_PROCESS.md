# Release process

The exact sequence to ship a new build of Whisper Project. This is
written for the **private-distribution** workflow — a small group of
users on your distribution channel, not a public GitHub release.

Read this file before cutting a release. The exact commands +
ordering are below.

---

## Step 0 — Decide what's shipping

* Read `docs/SESSION_HANDOFF_NEXT.md` — "what's pending" should be
  empty / acknowledged.
* Read `docs/FINAL_FREEZE_AUDIT_2026-05-21.md` (or the most recent
  freeze audit). Every blocker for this release should be either
  closed or consciously deferred with rationale.
* Open `docs/CHANGELOG.md`. Drafting the changelog entry first
  helps you spot anything that didn't actually land.

## Step 1 — Bump the version

Bump `pyproject.toml` from the `*-dev` suffix to the release number.

```
- version = "0.8.0-dev"
+ version = "0.8.0"
```

This single change should be its own commit so a future `git blame`
can point at the version bump cleanly.

## Step 2 — Update the changelog

In `docs/CHANGELOG.md`:

* Add a dated entry under `## [Unreleased]` → bump it to
  `## [0.8.0] — YYYY-MM-DD`.
* Summarise: new features, fixes, breaking changes, deprecations.
* Link to the relevant commits when possible.

## Step 3 — Write release notes

Create `docs/RELEASE_NOTES_v0.8.0.md` (mirroring the v0.7.0 / v0.7.1
shape). Sections to include:

* **What's new** — user-facing additions.
* **What changed** — behaviour changes (incl. silent ones).
* **Migration notes** — anything users need to do (delete an old
  cache, rename a config, etc.). For private distribution, be
  generous here — your users will read this.
* **Bug fixes** — short list.
* **Known issues** — items deferred to the next release.

## Step 4 — Run the full validation matrix

All of these must be green BEFORE building:

```cmd
pyright app/ core/                          ::  0 errors, 0 warnings
pytest tests/ --ignore=tests/smoke          ::  full unit + real-file E2E
pytest tests/core/test_transcribe_smoke.py  ::  smoke + end-to-end
pytest tests/core/test_transcribe_end_to_end.py
```

If anything's red, fix it before continuing. **Do not** ship a known
flake — your users will hit it.

## Step 5 — Build the three deliverables

From the repo root, in order:

```cmd
:: Portable (single-file EXE, ~447 MB at v0.7.1)
pyinstaller --noconfirm --clean whisper_project_onefile.spec
::    →  dist\WhisperProject-vX.Y.Z-Portable.exe

:: One-dir build (input to Setup-Compact)
pyinstaller --noconfirm --clean whisper_project_onedir.spec
::    →  dist_onedir\WhisperProject\

:: Embed-Python tree (input to Setup-Standard)
build_embed_installer.bat
::    →  embed_build\

:: Setup-Compact installer
"C:\Users\Owner\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
::    →  dist_installer\WhisperProject-vX.Y.Z-Setup-Compact.exe

:: Setup-Standard installer
"C:\Users\Owner\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer_embed.iss
::    →  dist_installer\WhisperProject-vX.Y.Z-Setup-Standard.exe
```

Update the version-string portions of `installer.iss` /
`installer_embed.iss` (line ~13: `AppVersion=…`,
`OutputBaseFilename=…`) before running ISCC. The PyInstaller
specs read the version from `pyproject.toml` automatically.

## Step 6 — Manual install + uninstall test

This is the test that catches release blockers. Do not skip.

For EACH of the three deliverables:

1. **Fresh user profile** — delete (or rename):
   * `%LOCALAPPDATA%\WhisperProject\`
   * The previous version's install directory under
     `C:\Program Files\WhisperProject\`
2. **Install** — run the EXE / Setup; pick the default folder.
3. **First-launch** — confirm the hub-folder dialog appears.
   * For one variant: pick the default `<app>/hub`.
   * For one variant: pick `D:\models` (outside the install dir).
4. **Transcribe** — drop a short file into the Transcribe tab.
   * Wait for it to finish.
   * Confirm `.srt` + `.json` were written next to the source.
   * Open the JSON viewer; confirm segments load.
5. **Uninstall** — run the uninstaller (or use Add/Remove Programs).
   * Variant 1 (hub inside app): no prompt; hub gone with install.
   * Variant 2 (hub on D:): prompted to delete the hub. Click No
     once; verify hub stays. Reinstall + uninstall again; click
     Yes; verify hub is gone.

If any step fails, **fix the bug and rebuild from Step 5**. Do not
ship the release with a known install / uninstall regression.

## Step 7 — Tag + push

```cmd
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Force-push to a tag is pre-authorised in CLAUDE.md only for
v0.7.0 — for any newer tag you'd be re-tagging, which means
something went wrong; investigate before forcing.

## Step 8 — Distribute

Upload to your private channel:

* Three `*.exe` files
* The release notes (`docs/RELEASE_NOTES_vX.Y.Z.md`) — paste into
  the announcement.
* If the changelog mentioned migration notes (Step 3), repeat
  them in the announcement.

## Step 9 — Bump `pyproject.toml` to the next `-dev`

```
- version = "0.8.0"
+ version = "0.8.1-dev"
```

Commit. This signals on `main` that the next release is in progress
and prevents accidental re-release of the same artefact.

## Step 10 — Update SESSION_HANDOFF_NEXT.md

Set "Current state" to reflect the post-release state:

* Last release tag = vX.Y.Z
* Working branch = whatever's active for the next round
* Pending items = empty or "post-release tidy-up"

---

## Troubleshooting the release

### "Inno Setup compile failed"

Most often a Pascal-Script syntax error. The `[Code]` block is
parsed lazily — read the ISCC output carefully; it gives you a
line number inside the `.iss`.

### "PyInstaller built but the EXE crashes on launch"

* Run the EXE from a terminal so you can see the traceback
  (`WhisperProject-vX.Y.Z-Portable.exe`).
* Most common cause: a `hiddenimports` entry missing from the
  spec. Add the module name + rebuild.

### "First-launch hub dialog doesn't appear"

* `%LOCALAPPDATA%\WhisperProject\config.json` may have stale
  `hub_folder` value from a previous test. Delete the file and
  retry.
* Or: use `--safe-mode` to back up + reset config in one step.

### "Uninstall doesn't prompt to delete the hub"

* Confirm `installer.iss` (and `installer_embed.iss`) both contain
  the `[Code]` section with `CurUninstallStepChanged`.
* Confirm the parity test passes:
  `pytest tests/core/test_inno_uninstall_parser.py`.
* Confirm `config.json` actually has `hub_folder` set to a path
  OUTSIDE the install dir.

---

## Appendix — the long-term maintenance loop

Roughly every six months:

* Re-read `docs/SENIOR_REVIEW_2026-05-21.md` and the latest freeze
  audit. Items that survive two reviews are real technical debt;
  budget time to fix.
* Re-run `pyright app/ core/` on `main`. Tightening the baseline
  catches drift early.
* Confirm `requirements.txt` and `pyproject.toml` still agree.
* Bump major dependencies (faster-whisper, sherpa-onnx,
  pywhispercpp) one at a time, with a real-file E2E run between
  each. The model file format changes from time to time; the
  smoke test is your canary.

Update this document whenever the steps change. The version of
RELEASE_PROCESS.md that lives next to the tag is the one that
applied for that release.
