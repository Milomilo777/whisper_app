# Phase 1a Brief — Foundation (theme + platformdirs + logging)

This file is a self-contained brief for a fresh Claude Code (or Claude Console) session acting as the **second senior architect** on this project. Paste the whole file as the first message. The session is expected to implement, test, commit, and (with the user's confirmation at the end) push.

---

## Your role

You are the second architect. The first architect produced Phase 0 (correctness baseline + full documentation) — see `docs/CHANGELOG.md` Unreleased section and the `50a4fea` commit. Your job:

1. **Verify Phase 0 still holds** by running every test in `docs/PHASE_0_ACCEPTANCE.md`.
2. **Implement Phase 1a** — the three highest-leverage items from `docs/ROADMAP.md` Phase 1: theme (1.1), platformdirs migration (1.2), proper logging (1.3). Also tidy `requirements.txt` (1.5).
3. **Write and run Phase 1a acceptance tests** before declaring done.
4. **Commit incrementally** on the current branch — one commit per logical unit — and do not create a new branch.
5. **Fix anything that fails** in either acceptance pass. Iterate until the final JSON report says `"overall": "ACCEPTED"` for both Phase 0 and Phase 1a.
6. **Do not push.** At the end, stop and ask the user to confirm before any `git push`.

Authorization scope: you may install pip packages from the items listed below, edit any file in the repo, run the GUI for smoke tests, commit. You may NOT delete files unrelated to the brief, change `master` branch behavior on the remote, or call external services.

---

## Context — what the project is

A Windows desktop Tkinter app that:

- Downloads audio/video via vendored `bin/yt-dlp.exe` with optional automatic subtitles
- Transcribes locally with `faster-whisper`, running the model in a long-lived subprocess worker
- Uses a JSON-over-stdio protocol between the Tk app and the worker

Read in this order before touching code:

1. `README.md`
2. `docs/ARCHITECTURE.md` — process model, threading rules, cancellation contract
3. `docs/AUDIT.md` — known issues, what Phase 0 fixed
4. `docs/ROADMAP.md` Phase 1 — the menu you're picking from
5. `docs/DECISIONS.md` — load-bearing choices that constrain your refactor
6. `docs/PHASE_0_ACCEPTANCE.md` — the test plan you'll run first

---

## Step 1 — Run Phase 0 acceptance

Open `docs/PHASE_0_ACCEPTANCE.md` and run all eight tests exactly as specified. Record the JSON result in your scratchpad.

**Fail policy:** if any Phase 0 test fails, stop, investigate, fix on the current branch with a focused commit (commit message starts with `Phase 0 hotfix:`), and re-run the failing test. Do not proceed to Step 2 until Phase 0 returns `"overall": "ACCEPTED"`.

---

## Step 2 — Phase 1a: theme

ROADMAP item 1.1.

### Goal

The app no longer looks like 1995 Tk. Switch to Sun Valley theme with a user-selectable Light/Dark/System mode that persists.

### Tasks

- Add `sv-ttk>=2.6.0` to `requirements.txt` (uncomment the existing line)
- In `gui.py`, after `App.__init__` builds the root, call `sv_ttk.set_theme(self.app_config.get("theme", "dark"))`
- Add a `theme` field to `DEFAULT_CONFIG` in `core/config.py` (default `"dark"`)
- Add a Settings → Appearance submenu in the menubar (or a single `View → Theme` cascade) with three radio items: `Light`, `Dark`, `System`. Selecting one calls `sv_ttk.set_theme(...)` and persists via `save_config`
- The Transcribe tab uses raw `tk.Label`/`tk.Button`/`tk.Entry` (see AUDIT B4). Convert them to `ttk` equivalents so the theme applies consistently

### Acceptance for 1.1

```python
# Inline checks the implementer must run and embed in the final report
import sv_ttk  # must import without error
# After App() construction, the current theme must equal config['theme']
# A theme menu cascade must exist on the menubar
# tk.Label / tk.Button / tk.Entry should appear zero times in gui.py outside of the worker-tree-internal class definitions; ttk equivalents only
```

Commit message: `Phase 1.1: Sun Valley theme + ttk migration on Transcribe tab`

---

## Step 3 — Phase 1a: platformdirs

ROADMAP item 1.2.

### Goal

`config.json`, model cache, logs, and download history live under per-user paths (`%LOCALAPPDATA%\WhisperProject\...`) instead of next to the executable. The existing `config.json` is migrated on first launch.

### Tasks

- Add `platformdirs>=4.0.0` to `requirements.txt`
- In `core/config.py`:
  - Replace `user_cache_dir()` (currently a hand-rolled helper added in Phase 0) with `platformdirs.user_cache_dir("WhisperProject")` and `platformdirs.user_config_dir("WhisperProject")` and `platformdirs.user_log_dir("WhisperProject")`. Keep a thin wrapper so call sites don't change
  - Add a `migrate_config_location()` function: if the old `config.json` exists next to `__file__/..`, copy it to the new platformdirs path, rename the old one to `.migrated.bak`, and log it
  - `config_path()` returns the platformdirs path
- Update `core/transcriber.py` and `gui.py` references so they all go through `core.config.user_log_dir()` etc.
- Update `docs/CONFIG.md` — the new defaults and the migration note
- Update `.gitignore` if any new paths leak

### Acceptance for 1.2

The verifier should:

1. Move `config.json` to a test location matching the "old layout"
2. Launch the app headlessly (using the monkey-patch pattern from `docs/PHASE_0_ACCEPTANCE.md` test 8)
3. Confirm the file is moved to the platformdirs path, a `.migrated.bak` exists, and `load_config()` returns the migrated content
4. Confirm `model_path` and `download_folder` defaults in `DEFAULT_CONFIG` now point to platformdirs paths (or the empty string for `download_folder`, which the UI will set)
5. Confirm logging directory exists and is writable after first launch

Commit message: `Phase 1.2: migrate config + model cache + logs to platformdirs paths`

---

## Step 4 — Phase 1a: logging

ROADMAP item 1.3.

### Goal

Every module uses `logging.getLogger(__name__)`. Logs go to `<platformdirs.user_log_dir>/app.log` with rotation (5 MB × 3). The worker subprocess sends its log records over a dedicated channel that does not pollute the JSON stdio protocol. A "Help → Open log folder" menu item opens the directory.

### Tasks

- New module `core/logging_setup.py` with `setup_logging(level="INFO")`:
  - Configures a root `RotatingFileHandler` at `<user_log_dir>/app.log`, 5 MB × 3 backups, format `%(asctime)s %(levelname)s %(name)s — %(message)s`
  - Adds a `StreamHandler` to stderr at WARNING+ for visibility during development
  - Quiets noisy third-party loggers (`urllib3`, `requests`, `huggingface_hub`) to WARNING
- Call `setup_logging` from `gui.py` top-level (before `App()`) and from `core/worker.py` `main()`
- Replace every `print()` call in `gui.py`, `core/transcriber.py`, `core/worker.py`, `core/model_manager.py` with a logger call. Exception: the worker's JSON `emit()` function (the protocol channel) keeps using `print(..., flush=True)` to stdout because that IS the protocol
- The Tk-side console widget continues to receive log lines as today, but via a `QueueHandler` on a dedicated logger named `whisper.ui` (so the console stays as a user-visible feed of "what happened" rather than a debug dump)
- New menu item: `Help → Open log folder` that calls `os.startfile(user_log_dir())` on Windows, `subprocess.run(["xdg-open", ...])` on Linux, `subprocess.run(["open", ...])` on macOS

### Acceptance for 1.3

1. `grep -rn "print(" gui.py core/` returns zero matches (excepting the worker's `emit()` body)
2. After launching the app and triggering any action, `<user_log_dir>/app.log` exists and contains entries
3. `Help → Open log folder` menu item is present and (programmatically) the resolved path is the platformdirs log dir

Commit message: `Phase 1.3: standardize logging via core/logging_setup with rotating file handler`

---

## Step 5 — Update `requirements.txt`

ROADMAP item 1.5 (was already partially shipped in Phase 0).

### Tasks

- Move `sv-ttk` and `platformdirs` from the "Phase 1 additions (uncomment when implementing)" section to the active dependencies block
- Keep version pins at lower-bounds only
- Verify `pip install -r requirements.txt` succeeds on the user's Python 3.14 (the install log shows Python 3.14 in `C:\Python314`)

Commit message: `Phase 1.5: pull sv-ttk and platformdirs into active deps`

---

## Step 6 — Phase 1a acceptance plan

Create `docs/PHASE_1_ACCEPTANCE.md` modeled on `docs/PHASE_0_ACCEPTANCE.md`. Eight tests minimum, each grep-able. The required tests:

| ID | What it verifies | How |
|---|---|---|
| P1-T1 | sv-ttk imports and theme is set after App() construction | headless smoke + `app.tk.call("ttk::style", "theme", "use")` |
| P1-T2 | DEFAULT_CONFIG includes `theme` key | direct dict inspection |
| P1-T3 | Theme menu cascade exists | walk `app.menu` tree |
| P1-T4 | Transcribe tab uses ttk widgets exclusively | AST scan of `gui.py` |
| P1-T5 | `config_path()` resolves to platformdirs `user_config_dir` | call and assert prefix |
| P1-T6 | `migrate_config_location()` moves legacy `config.json` and writes `.migrated.bak` | scripted setup + call + assert |
| P1-T7 | `RotatingFileHandler` is attached to root logger after `setup_logging()` | inspect `logging.getLogger().handlers` |
| P1-T8 | No `print(` in core/ or gui.py outside `core/worker.py:emit()` | grep with allow-list |
| P1-T9 | "Open log folder" menu item exists and resolves to platformdirs log dir | walk menu tree |
| P1-T10 | All Phase 0 acceptance tests still pass | re-run `PHASE_0_ACCEPTANCE.md` end-to-end |

The acceptance doc must end with the same JSON output format as the Phase 0 doc. The verifier (a third agent or the user) should be able to paste the whole acceptance doc into a fresh session and get a deterministic pass/fail.

---

## Step 7 — Run Phase 1a acceptance

Run every test in `docs/PHASE_1_ACCEPTANCE.md`. Fail policy is identical: stop, fix, commit (`Phase 1 hotfix:`), re-run.

---

## Step 8 — Push and final report

When (and only when) both `PHASE_0_ACCEPTANCE` and `PHASE_1_ACCEPTANCE` return `"overall": "ACCEPTED"`:

1. Push to origin:

```bash
git push origin master
```

2. Capture the push outcome (commit shas pushed, any warnings).

3. Emit the combined JSON report below.

If push fails (credential helper missing, network error, sandbox block, anything), set `"push": {"status": "failed", "error": "<message>"}` in the report. Do not retry more than twice. Do not embed tokens in URLs.

If either acceptance is `"REJECTED"`, skip the push entirely. Emit the report with `"push": {"status": "skipped_due_to_failure"}` and the failure evidence. The user will decide whether to manually intervene.

Report shape:

```json
{
  "branch": "master",
  "commits_added": ["<sha>", "<sha>", "..."],
  "phase_0": { "overall": "ACCEPTED", "tests": { "T1_syntax": {...}, ... } },
  "phase_1a": { "overall": "ACCEPTED", "tests": { "P1-T1": {...}, ... } },
  "push": { "status": "ok", "remote": "origin/master", "head": "<sha>" }
}
```

After emitting the report, exit. The user does not need to be prompted to push — you already did it.

---

## Constraints and policy

- **Single branch.** All commits go on the branch HEAD points at when you start. If that's `master`, stay on `master`. Do not create or switch branches.
- **No history rewriting.** No rebases, no amends past the most recent commit, no force pushes. Each commit is additive.
- **No silent skips.** If a step is genuinely impossible (e.g., `sv-ttk` install fails on Python 3.14), commit the explanation as `docs/PHASE_1_BLOCKED.md` and stop. Don't fake green.
- **Test what you ship.** Every code change you make must be covered by an acceptance test you also write. If you can't write a test, write down why in `docs/PHASE_1_TESTING_GAPS.md`.
- **Respect AUDIT severity.** If your refactor uncovers a CRITICAL or HIGH item not in Phase 0, add a row to `docs/AUDIT.md` and fix it before continuing.
- **No new features.** Items 1.4 (split gui.py), 1.6 (test infra), 1.7 (type hints), 1.8 (Sentry) are explicitly out of scope for Phase 1a. They are Phase 1b, separate session.
- **No tokens in code or commits.** Never embed a GitHub PAT in a URL, a commit message, a config file, or any committed text. Use the host credential helper (GitHub Desktop on Windows leaves credentials in the Windows Credential Manager, which `git push` reads automatically). If push fails for credential reasons, surface the error in the JSON report and stop — do not ask the user for a token mid-session.

---

## Known traps from Phase 0 retrospective

- The user's Python is **3.14** (the install log shows `C:\Python314\`). Some packages may not have wheels yet — if `sv-ttk` or `platformdirs` install fails on Python 3.14, document and recommend a fallback (`pip install --no-deps` or alternative theme like `ttkbootstrap`)
- The user runs on Windows 10 — `os.startfile` is the correct way to open Explorer
- The `bin/` folder is gitignored. Do not commit anything in it
- The Tk app's main loop polls `queue.Queue`s at 100–300 ms. Avoid blocking that loop
- `core/worker.py` is a subprocess that talks JSON on stdout. Do NOT add any non-JSON `print()` to it. Logging must go to stderr or to a file

---

## Deliverables checklist

At end of session, the repo must contain:

- [ ] `docs/PHASE_1_ACCEPTANCE.md` — the test plan you wrote
- [ ] `core/logging_setup.py` — the new logging module
- [ ] `requirements.txt` — sv-ttk + platformdirs uncommented in active block
- [ ] Updated `gui.py` — theme menu, ttk migration on Transcribe tab, log calls instead of print
- [ ] Updated `core/config.py` — platformdirs paths, migration function, theme in defaults
- [ ] Updated `core/transcriber.py`, `core/worker.py`, `core/model_manager.py` — logger calls instead of print
- [ ] Updated `docs/CHANGELOG.md` — Unreleased section with Phase 1a entries
- [ ] Updated `docs/CONFIG.md` — new platformdirs paths documented
- [ ] Updated `docs/ROADMAP.md` — Phase 1.1, 1.2, 1.3, 1.5 marked DONE; 1.4, 1.6, 1.7, 1.8 still TODO

The final JSON report should be `"overall": "ACCEPTED"` for both phases. If not, the session is incomplete — do not declare done.
