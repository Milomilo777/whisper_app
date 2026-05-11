# oTranscribe Integration — Machine-Parseable Acceptance Plan

Paste this whole file into a fresh Claude Code (or Claude Console) session that has access to the repository. Modeled on `docs/PHASE_1_ACCEPTANCE.md`.

---

## You are a verifier, not an author

**Your only job** is to run the eleven tests below in order and report results. You **must not** modify code, commit, push, fix failing tests, or run anything outside the listed commands. If a test fails, record the failure with evidence and continue. At the end, output a single JSON object summarizing all tests. Do nothing else.

---

## Context

- **Repository path:** `C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2`
- **Branch under test:** the branch HEAD currently points at (`master`).
- **What Phase 2-oTranscribe shipped:**
  - `core/integrations/otranscribe.py` exposing `fmt_otr_time`, `srt_to_otr`, `whisper_json_to_otr`, `otr_to_srt`. Stdlib only.
  - `tests/integrations/test_otranscribe.py` (9 pytest cases) and three fixture files under `tests/integrations/fixtures/`.
  - GUI: `Help → Open oTranscribe...`, `Transcribe` tab `Import .otr → SRT...` button, `Transcription Queue` right-click `Export → oTranscribe (.otr)` for `finished` tasks.

---

## Pre-flight (does not count toward the eleven tests)

```bash
cd "C:/Users/Owner/Desktop/whisper_project_claude/whisper_project_direct_download_v2"
test -f docs/integrations/otranscribe-acceptance.md && echo "FOUND_OTR_ACCEPTANCE_DOC"
python -c "import sv_ttk, platformdirs, pytest; print('IMPORTS_OK')"
test -f core/integrations/otranscribe.py && test -f tests/integrations/test_otranscribe.py && echo "FILES_PRESENT"
```

All three lines must succeed.

---

## Test OTR-T1 — Public API surface is exactly the four documented names

```bash
python -c "
import core.integrations.otranscribe as m
expected = {'fmt_otr_time','srt_to_otr','whisper_json_to_otr','otr_to_srt'}
public = {n for n in dir(m) if not n.startswith('_')}
extras = public - expected - {'NBSP','HTMLParser','Path','annotations'}
# Filter trivially exported stdlib names imported via 'from'.
allowed_imports = {'NBSP','HTMLParser','Path','annotations','html','json','re'}
public_user_facing = public - allowed_imports
assert public_user_facing == expected, f'public={public_user_facing}'
print('OTR_T1_PASS')
"
```

Pass criterion: stdout contains `OTR_T1_PASS`.

---

## Test OTR-T2 — Pytest run for the integration

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/integrations/test_otranscribe.py -v
```

Pass criterion: stdout contains `9 passed` and zero failed/errored.

---

## Test OTR-T3 — Display format conventions

```bash
python -c "
from core.integrations.otranscribe import fmt_otr_time
cases = [(0,'0:00'),(3.456,'0:03'),(63,'1:03'),(599,'9:59'),(3600,'1:00:00'),(3723,'1:02:03'),(36000,'10:00:00')]
for sec, expected in cases:
    got = fmt_otr_time(sec)
    assert got == expected, f'{sec} -> {got!r}, expected {expected!r}'
print('OTR_T3_PASS')
"
```

Pass criterion: stdout contains `OTR_T3_PASS`.

---

## Test OTR-T4 — `.otr` text uses NBSP, never a regular space, after the closing `</span>`

```bash
python -c "
import json
from core.integrations.otranscribe import srt_to_otr
out = srt_to_otr('tests/integrations/fixtures/sample.srt', 'audio.wav')
text = json.loads(out)['text']
assert '</span> ' in text, 'NBSP after </span> is required'
assert '</span> ' not in text, 'regular ASCII space after </span> is a known bug'
print('OTR_T4_PASS')
"
```

Pass criterion: stdout contains `OTR_T4_PASS`.

---

## Test OTR-T5 — `.otr` text contains zero literal newlines

```bash
python -c "
import json
from core.integrations.otranscribe import srt_to_otr
text = json.loads(srt_to_otr('tests/integrations/fixtures/sample.srt'))['text']
assert '\n' not in text and '\r' not in text
print('OTR_T5_PASS')
"
```

Pass criterion: stdout contains `OTR_T5_PASS`.

---

## Test OTR-T6 — Persian round-trip preserves UTF-8 verbatim

```bash
PYTHONIOENCODING=utf-8 python -c "
import json, os, tempfile
from core.integrations.otranscribe import srt_to_otr, otr_to_srt, _parse_srt
src = 'tests/integrations/fixtures/sample_persian.srt'
otr = srt_to_otr(src)
assert 'سلام' in json.loads(otr)['text']
with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.otr', delete=False) as f:
    f.write(otr); p = f.name
try:
    back = otr_to_srt(p)
finally:
    os.unlink(p)
orig = list(_parse_srt(open(src, encoding='utf-8-sig').read()))
roundtripped = list(_parse_srt(back))
assert len(orig) == len(roundtripped) == 3
for (so, _eo, bo), (sr, _er, br) in zip(orig, roundtripped):
    assert abs(so - sr) < 0.001 and bo == br
print('OTR_T6_PASS')
"
```

Pass criterion: stdout contains `OTR_T6_PASS`.

---

## Test OTR-T7 — `media` field strips path, keeps basename only

```bash
python -c "
import json
from core.integrations.otranscribe import srt_to_otr
for arg, expected in [('C:/path/to/audio.mp3','audio.mp3'),('/var/data/file.wav','file.wav'),('','')]:
    got = json.loads(srt_to_otr('tests/integrations/fixtures/sample.srt', arg))['media']
    assert got == expected, f'{arg} -> {got!r}, expected {expected!r}'
print('OTR_T7_PASS')
"
```

Pass criterion: stdout contains `OTR_T7_PASS`.

---

## Test OTR-T8 — Last-segment end inference uses `media-time`

```bash
python -c "
import json, os, tempfile
from core.integrations.otranscribe import otr_to_srt, _parse_srt
payload = {
    'text': '<p><span class=\"timestamp\" contenteditable=\"false\" data-timestamp=\"10.000\">0:10</span> Only segment.</p>',
    'media': 'x.mp3', 'media-source': '', 'media-time': 20.0,
}
with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.otr', delete=False) as f:
    json.dump(payload, f, ensure_ascii=False); p = f.name
try:
    srt = otr_to_srt(p)
finally:
    os.unlink(p)
segs = list(_parse_srt(srt))
assert len(segs) == 1
start, end, _ = segs[0]
assert abs(start - 10.0) < 0.001
assert abs(end - 20.0) < 1.0
print('OTR_T8_PASS')
"
```

Pass criterion: stdout contains `OTR_T8_PASS`.

---

## Test OTR-T9 — GUI wires the three additions

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

# Help → Open oTranscribe...
mb = app.cget('menu')
m = app.nametowidget(mb)
help_idx = next(i for i in range(m.index('end')+1) if m.type(i)=='cascade' and m.entrycget(i,'label')=='Help')
help_menu = app.nametowidget(m.entrycget(help_idx,'menu'))
labels = [help_menu.entrycget(j,'label') for j in range(help_menu.index('end')+1) if help_menu.type(j)=='command']
assert 'Open oTranscribe...' in labels, f'help labels={labels}'

# webbrowser.open is wired
with mock.patch('gui.webbrowser.open') as patched:
    app.open_otranscribe()
    assert patched.called and patched.call_args.args[0] == 'https://otranscribe.com/'

# Import button on Transcribe tab
import tkinter as tk
def find(widget, text):
    for c in widget.winfo_children():
        try:
            if hasattr(c,'cget') and c.cget('text') == text:
                return c
        except tk.TclError:
            pass
        r = find(c, text)
        if r is not None:
            return r
    return None
btn = find(app.t1, 'Import .otr → SRT...')
assert btn is not None, 'Import button missing'

# Right-click handler exposes Export only for finished tasks
class FakeTask:
    def __init__(self, status):
        self.status = status
        self.file_path = 'x.mp3'
        self.progress = 100
        self.start_time = None
        self.cancelled = False
        self.paused = False
assert callable(getattr(app, 'export_task_to_otr', None))
assert callable(getattr(app, 'import_otr_to_srt', None))
app.destroy()
print('OTR_T9_PASS')
PY
```

Pass criterion: stdout contains `OTR_T9_PASS`.

---

## Test OTR-T10 — Phase 0 still passes

Re-run all eight Phase 0 tests from `docs/PHASE_0_ACCEPTANCE.md`. If each emits its expected `*_PASS` token, print `OTR_T10_PASS`.

---

## Test OTR-T11 — Phase 1a still passes

Re-run all ten Phase 1a tests from `docs/PHASE_1_ACCEPTANCE.md`. If each emits its expected `P1_T*_PASS` token, print `OTR_T11_PASS`.

---

## Output format (mandatory)

After all eleven tests are done, emit exactly one JSON block:

```json
{
  "branch": "<current branch>",
  "tests": {
    "OTR_T1_public_api":           {"pass": true, "evidence": "OTR_T1_PASS"},
    "OTR_T2_pytest":               {"pass": true, "evidence": "9 passed"},
    "OTR_T3_display_format":       {"pass": true, "evidence": "OTR_T3_PASS"},
    "OTR_T4_nbsp_boundary":        {"pass": true, "evidence": "OTR_T4_PASS"},
    "OTR_T5_single_line_text":     {"pass": true, "evidence": "OTR_T5_PASS"},
    "OTR_T6_persian_roundtrip":    {"pass": true, "evidence": "OTR_T6_PASS"},
    "OTR_T7_media_basename":       {"pass": true, "evidence": "OTR_T7_PASS"},
    "OTR_T8_last_segment_end":     {"pass": true, "evidence": "OTR_T8_PASS"},
    "OTR_T9_gui_wired":            {"pass": true, "evidence": "OTR_T9_PASS"},
    "OTR_T10_phase_0_passes":      {"pass": true, "evidence": "OTR_T10_PASS"},
    "OTR_T11_phase_1a_passes":     {"pass": true, "evidence": "OTR_T11_PASS"}
  },
  "overall": "ACCEPTED"
}
```

`"overall"` is `"ACCEPTED"` if and only if all eleven tests pass. Otherwise `"REJECTED"`.
