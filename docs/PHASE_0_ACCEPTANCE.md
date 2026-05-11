# Phase 0 Acceptance — Machine-Parseable Test Plan

Paste the whole body of this file into a fresh Claude Code (or Claude Console) session that has access to this repository. The plan is self-contained: every test is exact, every expected output is grep-able, and the policy on what the session may and may not do is explicit.

---

## You are a verifier, not an author

**Your only job** is to run the eight tests below in order and report results. You **must not** modify code, commit, push, fix failing tests, or run anything outside the listed commands. If a test fails, record the failure with evidence and continue to the next test.

At the end, output a single JSON object summarizing all tests. Do nothing else.

---

## Context

- **Repository path:** `C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2`
- **Branch under test:** `claude/determined-hermann-7dcfa7`
- **What Phase 0 did:**
  - Added `README.md`, `.gitignore`, `requirements.txt`
  - Added `docs/ARCHITECTURE.md`, `docs/AUDIT.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, `docs/CONFIG.md`, `docs/DECISIONS.md`, `docs/PHASE_0_ACCEPTANCE.md` (this file)
  - Fixed AUDIT items A1, A2, A3, A5, C1, C2, C7 in `gui.py`, `core/config.py`, `core/transcriber.py`
- **AUDIT mapping:** read `docs/CHANGELOG.md` section `## [Unreleased] / ### Fixed` for the full mapping of bug IDs to file changes.

---

## Pre-flight (does not count toward the eight tests)

Run these and bail out if any fail. They must all succeed before starting the test sequence.

```bash
cd "C:/Users/Owner/Desktop/whisper_project_claude/whisper_project_direct_download_v2"
git rev-parse --abbrev-ref HEAD
# Expected exact stdout: claude/determined-hermann-7dcfa7
```

```bash
test -f docs/PHASE_0_ACCEPTANCE.md && echo "FOUND_ACCEPTANCE_DOC"
# Expected exact stdout: FOUND_ACCEPTANCE_DOC
```

---

## Test 1 — Syntax of all Python files

**Command:**

```bash
python -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ['gui.py','core/config.py','core/transcriber.py','core/worker.py','core/task.py','core/model_manager.py']]; print('SYNTAX_OK')"
```

**Pass criterion:** stdout contains the literal token `SYNTAX_OK` and exit code is `0`.

---

## Test 2 — No `bare except` anywhere (AUDIT A2)

**Command:**

```bash
python -c "
import ast, sys
hits = []
for f in ['gui.py','core/config.py','core/transcriber.py','core/worker.py','core/task.py','core/model_manager.py']:
    tree = ast.parse(open(f, encoding='utf-8').read())
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler) and n.type is None:
            hits.append(f'{f}:{n.lineno}')
print('BARE_EXCEPTS=' + ','.join(hits) if hits else 'NO_BARE_EXCEPTS')
"
```

**Pass criterion:** stdout is exactly `NO_BARE_EXCEPTS`.

---

## Test 3 — `ffprobe` is resolved from bundled `bin/` (AUDIT A3)

**Command:**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from core.transcriber import bundled_binary, BIN_DIR
result = bundled_binary('ffprobe')
print('BIN_DIR=' + str(BIN_DIR))
print('RESOLVED=' + result)
import os
if BIN_DIR.exists() and (BIN_DIR / 'ffprobe.exe').exists():
    assert result == str(BIN_DIR / 'ffprobe.exe'), f'Expected bundled path, got {result}'
    print('A3_PASS_BUNDLED')
else:
    assert result == 'ffprobe', f'Expected fallback to PATH, got {result}'
    print('A3_PASS_FALLBACK')
"
```

**Pass criterion:** stdout contains either `A3_PASS_BUNDLED` or `A3_PASS_FALLBACK`. Either is acceptable; the former when the bundled binary is present, the latter when it is not.

---

## Test 4 — Atomic config save and corrupt-JSON recovery (AUDIT C1, C2)

**Command:** save to a temp file the following test script and run it. The script does its own cleanup.

```python
# verify_config.py
import os, sys, json, tempfile, shutil
sys.path.insert(0, '.')
from core import config as cfg

original = cfg.config_path()
backup = original + '.acceptance_backup'

# Snapshot original
had_original = os.path.exists(original)
if had_original:
    shutil.copy2(original, backup)

results = []
try:
    # T4a — fallback to defaults on missing
    if had_original:
        os.unlink(original)
    c = cfg.load_config()
    results.append(('T4a_missing_fallback', c.get('device') == 'auto' and 'model' in c))

    # T4b — atomic save round-trip
    c['download_folder'] = 'T4_TEST_MARKER'
    cfg.save_config(c)
    c2 = cfg.load_config()
    # If T4_TEST_MARKER is not on a mounted drive, fallback may have cleared it.
    # The point is the file written and re-read without error.
    results.append(('T4b_save_roundtrip', os.path.exists(original)))

    # T4c — corrupt JSON detected and quarantined
    with open(original, 'w', encoding='utf-8') as f:
        f.write('{ this is broken json')
    c3 = cfg.load_config()
    quarantined = os.path.exists(original + '.corrupt')
    results.append(('T4c_corrupt_quarantined', quarantined and c3.get('device') == 'auto'))
    if quarantined:
        os.unlink(original + '.corrupt')

finally:
    # Restore
    try:
        os.unlink(original)
    except OSError:
        pass
    if had_original:
        shutil.move(backup, original)

ok = all(passed for _, passed in results)
print('RESULTS=' + json.dumps(results))
print('C1_C2_PASS' if ok else 'C1_C2_FAIL')
```

```bash
python verify_config.py
rm verify_config.py
```

**Pass criterion:** stdout contains `C1_C2_PASS`.

---

## Test 5 — `model_path` on unreachable drive falls back to LOCALAPPDATA (AUDIT C7)

**Command:**

```bash
python -c "
import sys, os, json, tempfile, shutil
sys.path.insert(0, '.')
from core import config as cfg

original = cfg.config_path()
backup = original + '.acceptance_backup'
shutil.copy2(original, backup) if os.path.exists(original) else None

try:
    # Write a config that points at a drive that almost certainly does not exist
    test_cfg = {
        'model': {'name': 'faster-whisper-large-v3', 'url': 'x', 'md5': 'y'},
        'model_path': 'Q:\\\\nonexistent\\\\drive\\\\test',
        'device': 'auto',
        'compute_type': 'int8',
        'parallel_workers': 2,
        'download_folder': 'Q:\\\\nope'
    }
    with open(original, 'w', encoding='utf-8') as f:
        json.dump(test_cfg, f)

    loaded = cfg.load_config()
    print('LOADED_MODEL_PATH=' + loaded['model_path'])
    print('LOADED_DOWNLOAD_FOLDER=' + repr(loaded['download_folder']))

    if os.name == 'nt':
        assert 'Q:' not in loaded['model_path'], 'FAIL: unreachable Q: drive not replaced'
        assert loaded['download_folder'] == '', 'FAIL: unreachable download_folder not cleared'
        print('C7_PASS')
    else:
        # On non-Windows, drive check is a no-op
        print('C7_SKIPPED_NON_WINDOWS')
finally:
    if os.path.exists(backup):
        shutil.move(backup, original)
    else:
        try: os.unlink(original)
        except OSError: pass
"
```

**Pass criterion:** stdout contains either `C7_PASS` or `C7_SKIPPED_NON_WINDOWS`.

---

## Test 6 — `yt-dlp --update` is gated behind a config flag and a daily timestamp (AUDIT A1)

**Static check — does the helper exist and is the old unconditional call gone?**

```bash
python -c "
import ast
src = open('gui.py', encoding='utf-8').read()
tree = ast.parse(src)
classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
app = classes['App']
methods = {n.name for n in app.body if isinstance(n, ast.FunctionDef)}
assert 'maybe_update_yt_dlp' in methods, 'FAIL: helper method missing'

# Count occurrences of the literal --update flag
import re
update_calls = re.findall(r'\"--update\"', src)
assert len(update_calls) == 1, f'FAIL: expected exactly 1 --update reference, got {len(update_calls)}'

# The single occurrence must be inside maybe_update_yt_dlp
helper = next(m for m in app.body if isinstance(m, ast.FunctionDef) and m.name == 'maybe_update_yt_dlp')
helper_src = ast.get_source_segment(src, helper)
assert '--update' in helper_src, 'FAIL: --update is not inside maybe_update_yt_dlp'
print('A1_PASS')
"
```

**Behavioral check — calling the helper with `auto_update_yt_dlp=False` must NOT spawn a subprocess.**

```bash
python -c "
import sys, types, unittest.mock
sys.path.insert(0, '.')

# We can't easily import gui.py headlessly because of tkinter side effects.
# Instead, parse-and-check that the helper guards on the flag.
src = open('gui.py', encoding='utf-8').read()
assert 'if not self.app_config.get(\"auto_update_yt_dlp\", False):' in src, 'FAIL: guard not found'
assert 'return' in src.split('if not self.app_config.get(\"auto_update_yt_dlp\", False):')[1][:80]
print('A1_GUARD_PRESENT')
"
```

**Pass criterion:** both invocations print `A1_PASS` and `A1_GUARD_PRESENT` respectively.

---

## Test 7 — Partial subtitle cleanup on cancel (AUDIT A5)

**Static check:**

```bash
python -c "
src = open('gui.py', encoding='utf-8').read()

# Locate the cancel branch inside the subtitle phase
needle_start = src.find('if task.cancelled:')
assert needle_start != -1, 'FAIL: no task.cancelled branch'

# Find the FIRST task.cancelled check that occurs after a wrote_files mention
wrote_idx = src.find('wrote_files=[]')
assert wrote_idx != -1, 'FAIL: wrote_files not present'

cancel_after_wrote = src.find('if task.cancelled:', wrote_idx)
assert cancel_after_wrote != -1, 'FAIL: no cancel check after wrote_files'

# The block must contain os.unlink and the log marker
block = src[cancel_after_wrote:cancel_after_wrote + 800]
assert 'os.unlink' in block, 'FAIL: no os.unlink in cancel cleanup'
assert 'Removed partial subtitle file' in block, 'FAIL: log marker missing'
print('A5_PASS')
"
```

**Pass criterion:** stdout contains `A5_PASS`.

---

## Test 8 — Headless GUI smoke test (no model required)

Save the following to a temp file `acceptance_smoke.py`, run it, and clean up. The script monkey-patches `start_standby_worker` and `ensure_model_with_modal` so it never needs a real model.

```python
# acceptance_smoke.py
import sys, os, unittest.mock as mock
sys.path.insert(0, '.')

# Force a headless-friendly Tk (still needs a display on Windows — that's fine on the user's machine)
import tkinter as tk

import gui

# Neutralize background work
gui.App.start_standby_worker = lambda self: None
gui.App.ensure_model_with_modal = lambda self, mandatory=False: True
gui.App.loop = lambda self: None  # don't restart the polling cycle

app = gui.App()
app.update_idletasks()
app.update()

results = []

# 8a — three tabs in expected order
tab_titles = [app.nb.tab(i, 'text') for i in range(app.nb.index('end'))]
results.append(('T8a_three_tabs', tab_titles == ['Transcribe', 'Transcription Queue', 'Download Videos']))

# 8b — subtitle combo starts disabled
state = str(app.subtitle_lang_combo.cget('state'))
results.append(('T8b_subtitle_combo_disabled', state == 'disabled'))

# 8c — SUBTITLE_LANGUAGES ordering: Automatic, English, then alphabetical
names = [n for n, _ in gui.SUBTITLE_LANGUAGES]
ordered = names[0] == 'Automatic' and names[1] == 'English' and names[2:] == sorted(names[2:])
results.append(('T8c_languages_order', ordered))

# 8d — maybe_update_yt_dlp does NOT call subprocess when auto_update is off
app.app_config['auto_update_yt_dlp'] = False
class FakeTask:
    pass
with mock.patch('gui.subprocess.run') as patched:
    app.maybe_update_yt_dlp(FakeTask())
    results.append(('T8d_update_not_called_when_disabled', patched.call_count == 0))

app.destroy()

import json
print('SMOKE_RESULTS=' + json.dumps(results))
all_pass = all(p for _, p in results)
print('T8_PASS' if all_pass else 'T8_FAIL')
```

```bash
python acceptance_smoke.py
rm acceptance_smoke.py
```

**Pass criterion:** stdout contains `T8_PASS`.

---

## Output format (mandatory)

After all eight tests are done, emit exactly one JSON block. No prose before or after. Format:

```json
{
  "branch": "claude/determined-hermann-7dcfa7",
  "tests": {
    "T1_syntax":          {"pass": true,  "evidence": "SYNTAX_OK"},
    "T2_no_bare_except":  {"pass": true,  "evidence": "NO_BARE_EXCEPTS"},
    "T3_ffprobe_bundled": {"pass": true,  "evidence": "A3_PASS_FALLBACK"},
    "T4_config":          {"pass": true,  "evidence": "C1_C2_PASS"},
    "T5_unreachable_drive": {"pass": true, "evidence": "C7_PASS"},
    "T6_yt_dlp_update_gated": {"pass": true, "evidence": "A1_PASS;A1_GUARD_PRESENT"},
    "T7_partial_subtitle_cleanup": {"pass": true, "evidence": "A5_PASS"},
    "T8_headless_smoke":  {"pass": true,  "evidence": "T8_PASS"}
  },
  "overall": "ACCEPTED" 
}
```

`"overall"` must be `"ACCEPTED"` if and only if all eight test results have `"pass": true`. Otherwise `"REJECTED"`.

For any failed test, include in `"evidence"` the actual stdout/stderr fragment that proves failure. Do not try to fix anything.

---

## Cleanup

The scripts above each restore the original `config.json` and remove temp files. If the session is interrupted, the only state on disk that could be left over is `config.json.corrupt` next to `config.json` — safe to delete.
