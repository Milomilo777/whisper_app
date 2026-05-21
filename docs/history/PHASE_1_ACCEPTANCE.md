# Phase 1a Acceptance — Machine-Parseable Test Plan

Paste this entire file into a fresh Claude Code (or Claude Console) session that has access to the repository. Modeled on `PHASE_0_ACCEPTANCE.md`.

---

## You are a verifier, not an author

**Your only job** is to run the ten tests below in order and report results. You **must not** modify code, commit, push, fix failing tests, or run anything outside the listed commands. If a test fails, record the failure with evidence and continue. At the end, output a single JSON object summarizing all tests. Do nothing else.

---

## Context

- **Repository path:** `C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2`
- **Branch under test:** the branch HEAD currently points at (`master` for the developer's machine).
- **What Phase 1a did:**
  - Sun Valley theme via `sv-ttk` + `View → Theme` cascade with Light/Dark/System radiobuttons + `theme` and `log_level` keys in `DEFAULT_CONFIG`.
  - Migrated `config.json`, model cache, and logs to `platformdirs.user_*_dir("WhisperProject")`.
  - Centralized logging through `core/logging_setup.py` with a `RotatingFileHandler` (5 MB × 3) at `<user_log_dir>/app.log`, plus `Help → Open log folder`.
  - Promoted `sv-ttk` and `platformdirs` to active deps in `requirements.txt`.

---

## Pre-flight (does not count toward the ten tests)

```bash
cd "C:/Users/Owner/Desktop/whisper_project_claude/whisper_project_direct_download_v2"
test -f docs/PHASE_1_ACCEPTANCE.md && echo "FOUND_PHASE_1_DOC"
python -c "import sv_ttk, platformdirs; print('IMPORTS_OK')"
```

Both lines must succeed.

---

## Test P1-T1 — Theme is applied after `App()` construction

```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
import sys; sys.path.insert(0, '.')
import gui
gui.App.start_standby_worker = lambda self: None
gui.App.ensure_model_with_modal = lambda self, mandatory=False: True
gui.App.loop = lambda self: None
app = gui.App()
app.update_idletasks(); app.update()
current = app.tk.call("ttk::style", "theme", "use")
assert "sun-valley" in current, f"FAIL: expected sun-valley theme, got {current}"
app.destroy()
print("P1_T1_PASS:" + current)
PY
```

Pass criterion: stdout contains `P1_T1_PASS:sun-valley-` followed by `light` or `dark`.

---

## Test P1-T2 — `DEFAULT_CONFIG` includes `theme`

```bash
python -c "from core.config import DEFAULT_CONFIG; assert 'theme' in DEFAULT_CONFIG and DEFAULT_CONFIG['theme'] in ('light','dark','system'); print('P1_T2_PASS')"
```

Pass criterion: stdout is `P1_T2_PASS`.

---

## Test P1-T3 — `View → Theme` cascade with three radio items

```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
import sys; sys.path.insert(0, '.')
import gui
gui.App.start_standby_worker = lambda self: None
gui.App.ensure_model_with_modal = lambda self, mandatory=False: True
gui.App.loop = lambda self: None
app = gui.App()
app.update_idletasks(); app.update()
mb = app.cget('menu')
m = app.nametowidget(mb)
view_idx = None
for i in range(m.index('end')+1):
    if m.type(i) == 'cascade' and m.entrycget(i,'label') == 'View':
        view_idx = i
        break
assert view_idx is not None, "FAIL: View cascade missing"
view_menu = app.nametowidget(m.entrycget(view_idx,'menu'))
items = []
for j in range(view_menu.index('end')+1):
    if view_menu.type(j) == 'radiobutton':
        items.append(view_menu.entrycget(j,'label'))
assert items == ['Light','Dark','System'], f"FAIL: items={items}"
app.destroy()
print("P1_T3_PASS")
PY
```

Pass criterion: stdout contains `P1_T3_PASS`.

---

## Test P1-T4 — Transcribe tab uses `ttk` widgets exclusively

```bash
python - <<'PY'
import ast
src = open('gui.py', encoding='utf-8').read()
tree = ast.parse(src)
hits = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name) and node.func.value.id == 'tk' and node.func.attr in ('Label','Button','Entry'):
            hits.append((node.func.attr, node.lineno))
assert not hits, f"FAIL: tk.* widget calls remain: {hits}"
print("P1_T4_PASS")
PY
```

Pass criterion: stdout is `P1_T4_PASS`.

---

## Test P1-T5 — `config_path()` resolves under `platformdirs.user_config_dir`

```bash
python - <<'PY'
import platformdirs
from core.config import config_path
expected_prefix = platformdirs.user_config_dir("WhisperProject", False)
actual = config_path()
assert actual.startswith(expected_prefix), f"FAIL: {actual} not under {expected_prefix}"
print("P1_T5_PASS:" + actual)
PY
```

Pass criterion: stdout starts with `P1_T5_PASS:`.

---

## Test P1-T6 — `migrate_config_location()` moves a legacy `config.json` and writes `.migrated.bak`

```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
import os, sys, json, shutil, tempfile
sys.path.insert(0, '.')
from core import config as cfg

new_path = cfg.config_path()
legacy = cfg._legacy_config_path()

# Snapshot whatever is on disk so we can restore
new_backup = new_path + '.t6backup' if os.path.exists(new_path) else None
if new_backup:
    shutil.copy2(new_path, new_backup)
    os.unlink(new_path)
legacy_backup = legacy + '.t6backup' if os.path.exists(legacy) else None
if legacy_backup:
    shutil.copy2(legacy, legacy_backup)

bak_path = legacy + '.migrated.bak'
bak_backup = bak_path + '.t6backup' if os.path.exists(bak_path) else None
if bak_backup:
    shutil.copy2(bak_path, bak_backup)
    os.unlink(bak_path)

results = []
try:
    payload = {
        'model': {'name':'faster-whisper-large-v3','url':'x','md5':'y'},
        'model_path': '', 'device': 'auto', 'compute_type':'int8',
        'parallel_workers': 2, 'download_folder': '',
        'theme':'dark','log_level':'INFO',
    }
    with open(legacy, 'w', encoding='utf-8') as f:
        json.dump(payload, f)
    cfg.migrate_config_location()
    moved = os.path.exists(new_path) and not os.path.exists(legacy) and os.path.exists(bak_path)
    results.append(('moved_and_bak', moved))
    loaded = cfg.load_config()
    results.append(('loaded_keys_present', set(payload.keys()).issubset(set(loaded.keys()))))
finally:
    # Cleanup: remove anything we created
    for p in (new_path, legacy, bak_path):
        try: os.unlink(p)
        except OSError: pass
    # Restore originals
    if new_backup:
        shutil.move(new_backup, new_path)
    if legacy_backup:
        shutil.move(legacy_backup, legacy)
    if bak_backup:
        shutil.move(bak_backup, bak_path)

ok = all(p for _, p in results)
print('RESULTS=' + json.dumps(results))
print('P1_T6_PASS' if ok else 'P1_T6_FAIL')
PY
```

Pass criterion: stdout contains `P1_T6_PASS`.

---

## Test P1-T7 — `RotatingFileHandler` is attached to root after `setup_logging()`

```bash
python - <<'PY'
import logging
from core.logging_setup import setup_logging
setup_logging('INFO')
handler_types = {type(h).__name__ for h in logging.getLogger().handlers}
assert 'RotatingFileHandler' in handler_types, f"FAIL: handlers={handler_types}"
print('P1_T7_PASS')
PY
```

Pass criterion: stdout is `P1_T7_PASS`.

---

## Test P1-T8 — No `print(` in `core/` or `gui.py` outside the worker's `emit()`

```bash
python - <<'PY'
import ast
hits = []
for f in ('gui.py','core/config.py','core/transcriber.py','core/worker.py','core/model_manager.py','core/logging_setup.py','core/task.py'):
    src = open(f, encoding='utf-8').read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'print':
            enclosing = None
            for parent in ast.walk(tree):
                if isinstance(parent, ast.FunctionDef):
                    if parent.lineno <= node.lineno <= (parent.end_lineno or node.lineno):
                        enclosing = parent.name
            if f == 'core/worker.py' and enclosing == 'emit':
                continue
            hits.append((f, node.lineno, enclosing))
assert not hits, f"FAIL: print calls remain: {hits}"
print('P1_T8_PASS')
PY
```

Pass criterion: stdout is `P1_T8_PASS`.

---

## Test P1-T9 — `Help → Open log folder` exists and resolves to platformdirs log dir

```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
import sys, unittest.mock as mock
sys.path.insert(0, '.')
import gui
gui.App.start_standby_worker = lambda self: None
gui.App.ensure_model_with_modal = lambda self, mandatory=False: True
gui.App.loop = lambda self: None
app = gui.App()
app.update_idletasks(); app.update()
mb = app.cget('menu')
m = app.nametowidget(mb)
help_idx = None
for i in range(m.index('end')+1):
    if m.type(i)=='cascade' and m.entrycget(i,'label')=='Help':
        help_idx = i; break
assert help_idx is not None, 'FAIL: Help cascade missing'
help_menu = app.nametowidget(m.entrycget(help_idx,'menu'))
labels = [help_menu.entrycget(j,'label') for j in range(help_menu.index('end')+1) if help_menu.type(j)=='command']
assert 'Open log folder' in labels, f'FAIL: items={labels}'

import os
with mock.patch.object(os, 'startfile', create=True) as patched_startfile:
    app.open_log_folder()
    assert patched_startfile.called, 'FAIL: open_log_folder did not call os.startfile'
    arg = patched_startfile.call_args.args[0]
    import platformdirs
    expected = platformdirs.user_log_dir('WhisperProject', False)
    assert arg.startswith(expected), f'FAIL: opened {arg}, expected prefix {expected}'
app.destroy()
print('P1_T9_PASS')
PY
```

Pass criterion: stdout is `P1_T9_PASS`.

---

## Test P1-T10 — All Phase 0 acceptance tests still pass

Re-run each of the eight tests from `docs/PHASE_0_ACCEPTANCE.md` exactly as specified there. The verifier's helper:

```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
import subprocess, sys
out = subprocess.run([sys.executable, '-c', "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ['gui.py','core/config.py','core/transcriber.py','core/worker.py','core/task.py','core/model_manager.py']]; print('SYNTAX_OK')"], capture_output=True, text=True)
print('T1:', 'OK' if 'SYNTAX_OK' in out.stdout else 'FAIL')
PY
```

The full re-run is automated via `python -m pytest` in Phase 1b. For now, the verifier should manually paste each Phase 0 test command from `PHASE_0_ACCEPTANCE.md` and confirm each ends in its expected `*_PASS` marker. If all eight produce their expected marker, print `P1_T10_PASS`.

Pass criterion: stdout contains `P1_T10_PASS` after running all eight Phase 0 tests.

---

## Output format (mandatory)

After all ten tests are done, emit exactly one JSON block:

```json
{
  "branch": "<current branch>",
  "tests": {
    "P1_T1_theme_applied":         {"pass": true, "evidence": "P1_T1_PASS:sun-valley-dark"},
    "P1_T2_default_config_theme":  {"pass": true, "evidence": "P1_T2_PASS"},
    "P1_T3_view_theme_cascade":    {"pass": true, "evidence": "P1_T3_PASS"},
    "P1_T4_ttk_only_transcribe":   {"pass": true, "evidence": "P1_T4_PASS"},
    "P1_T5_platformdirs_config":   {"pass": true, "evidence": "P1_T5_PASS:..."},
    "P1_T6_migration":             {"pass": true, "evidence": "P1_T6_PASS"},
    "P1_T7_rotating_handler":      {"pass": true, "evidence": "P1_T7_PASS"},
    "P1_T8_no_print":              {"pass": true, "evidence": "P1_T8_PASS"},
    "P1_T9_open_log_folder":       {"pass": true, "evidence": "P1_T9_PASS"},
    "P1_T10_phase_0_still_passes": {"pass": true, "evidence": "P1_T10_PASS"}
  },
  "overall": "ACCEPTED"
}
```

`"overall"` is `"ACCEPTED"` if and only if all ten tests pass. Otherwise `"REJECTED"`.
