# Supreme Master TV Integration — Acceptance Plan

This file is the grep-able checklist for SMTV-T1 … SMTV-T8. Each
token has a runnable command (where possible) and the exact string
that must appear in the output to count as PASS.

Read `docs/integrations/smtv-research.md` for the *why* and
`docs/integrations/smtv-brief.md` for the *what was built*.

---

## Pre-flight

```bash
cd C:/Users/Owner/Desktop/whisper_project_claude/whisper_project_direct_download_v2
python -c "import core.integrations.smtv as m; print('SMTV_IMPORT_OK', m.__name__)"
test -f core/integrations/smtv.py && echo "FILES_PRESENT"
test -f docs/integrations/smtv-research.md && test -f docs/integrations/smtv-brief.md && echo "DOCS_PRESENT"
```

All three must succeed.

---

## SMTV-T1 — yt-dlp is not in the SMTV path; `is_smtv_url` recognises the URL

The brief mandates that yt-dlp is **not** invoked for SMTV episodes.
The public recogniser must accept every observed shape.

```bash
python -c "
from core.integrations.smtv import is_smtv_url, parse_episode_id
assert is_smtv_url('https://suprememastertv.com/en1/v/314924375480.html')
assert is_smtv_url('https://suprememastertv.com/fa1/v/314324511501.html')
assert not is_smtv_url('https://youtube.com/watch?v=abc')
assert parse_episode_id('https://suprememastertv.com/en1/v/314924375480.html') == ('en','314924375480')
print('SMTV-T1 PASS')
"
```

Expected on stdout: `SMTV-T1 PASS`.

Secondary check (no yt-dlp subprocess for SMTV URLs):

```
grep -nC2 "yt-dlp\|yt_dlp" app/services/download_service.py | grep -B1 -A1 "smtv"
```

Should return **no lines**.

---

## SMTV-T2 — Live page yields a sibling list when episode is part of a series

```bash
python -c "
from core.integrations import smtv
ep = smtv.fetch_episode('https://suprememastertv.com/en1/v/314924375480.html')
print('vid:', ep.vid)
print('siblings:', len(ep.siblings))
assert len(ep.siblings) >= 6, ep.siblings
print('SMTV-T2 PASS')
"
```

Requires network reachability to `suprememastertv.com`. Expected
final line: `SMTV-T2 PASS`. With the reference URL (Part 7 of 7),
six siblings (Parts 1..6) come back.

---

## SMTV-T3 — Reference episode downloads as MP4 via the app

**Manual workflow** (UI driven; no script substitute, by design):

1. Launch `dist\WhisperProject.exe` (or the installer's
   `WhisperProject.exe` from `C:\Temp\installed_test\` or whatever
   install directory the user picked).
2. Switch to the **Download Videos** tab.
3. Paste
   `https://suprememastertv.com/en1/v/314324511501.html` into the URL
   field. Wait ~ 2–3 s for the status line to switch from "Loading"
   to "SMTV episode loaded: 3 video / 1 audio formats; 6 sibling
   parts detected".
4. Pick **HD 720p** in the video dropdown. Uncheck "Download all
   parts of this series (SMTV)" if it is on (defaults to on).
5. Click **Download**.
6. Wait for status to read `finished`.
7. Verify that `<folder>\3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7-2m.mp4`
   exists and that its size matches the CDN's `Content-Length`
   advertised by `curl -sI` on the same URL.

PASS criterion: the file exists, size > 100 MB, opens in any media
player.

---

## SMTV-T4 — MP3 audio mode downloads the audio-only file

**Manual workflow:**

1. Same URL as SMTV-T3.
2. Switch the Mode dropdown to **Audio**. The audio-format dropdown
   should show `MP3 (audio only)` as the only option.
3. Click **Download**.
4. Verify `<folder>\3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7.mp3`
   exists. `file <name>.mp3` should report an MPEG audio header.

The MP3 is served directly by the CDN; **no ffmpeg conversion** is
invoked. Confirm by checking `bin\ffmpeg.exe` is not spawned during
the download (Task Manager or `Get-Process | Where Name -like
'ffmpeg*'`).

---

## SMTV-T5 — Page transcript is saved as a sibling `.txt` file

The episode's page-embedded transcript (the article body) is
extracted and written next to the downloaded media. Mirrors the
audio basename when present, the video basename otherwise.

**Manual workflow** (continuing from T3 or T4):

```bash
ls <folder>/3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7.txt
head -1 <folder>/3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7.txt
```

PASS criterion: the `.txt` file exists, contains the page transcript
(starts with `"You guys are experts at eating."` for Part 1 of this
specific series), and reads as clean UTF-8 (Persian / Chinese
transcripts on `/fa1/` and `/ch1/` survive without mojibake).

---

## SMTV-T6 — Auto-transcribe-after-download wires up unchanged

The SMTV download path emits a `done_full` event with the saved-file
path, exactly like the YouTube flow. With `auto_transcribe_after_download`
enabled, the saved MP4 lands in the Transcription Queue.

**Manual workflow:**

1. In the Download tab, check **"Transcribe after download"**.
2. Repeat SMTV-T3 with the 720p MP4.
3. After the download finishes, switch to the **Transcription Queue**
   tab. A new task for the just-downloaded MP4 should be present and
   either `waiting`/`running`/`finished` depending on timing.
4. After whisper transcribes it, confirm `<base>.srt` and `<base>.json`
   sit alongside both the MP4 and the SMTV `<base>.txt` from T5.

PASS criterion: three transcript outputs co-exist —
`<base>.txt` (page transcript), `<base>.srt` and `<base>.json`
(whisper).

---

## SMTV-T7 — No regression in the unit suite

```bash
python -m pytest tests/ --ignore=tests/smoke -q
```

Expected tail: `162 passed`. Adding SMTV brought 23 new tests on top
of the prior 139. Any number below 162 means a regression.

---

## SMTV-T8 — Both deliverables still transcribe a real video

Onefile portable:

```bash
rm -f "E:\3029-NWN-Daily-Scroll-2m_0002.srt" "E:\3029-NWN-Daily-Scroll-2m_0002.json"
python -m pytest tests/smoke/test_exe_real_e2e.py -v -s
```

Expected: `3 passed`.

Installed copy (from the dual-deliverable installer):

```bash
WHISPER_SMOKE_EXE="C:\Temp\installed_test\WhisperProject.exe" \
python -m pytest tests/smoke/test_exe_real_e2e.py::test_exe_worker_transcribes_real_video -v -s
```

Expected: `1 passed`.

Both must succeed against the rebuilt artefacts. Proof that
`core.integrations.smtv` is correctly bundled in both packaging
modes.

---

## Live SMTV smoke (optional, ~ 3 s, requires network)

```bash
python -m pytest tests/smoke/test_smtv_smoke.py -v
```

Expected: `2 passed`. Skipped when `WHISPER_OFFLINE_TESTS=1` or
when the SMTV host is unreachable.

---

## Final report block (machine-parseable)

After every check above, emit one JSON object like:

```json
{
  "feature": "smtv",
  "branch": "release/single-file-exe",
  "tests": {
    "SMTV-T1": "PASS",
    "SMTV-T2": "PASS",
    "SMTV-T3": "PASS|MANUAL_PENDING",
    "SMTV-T4": "PASS|MANUAL_PENDING",
    "SMTV-T5": "PASS|MANUAL_PENDING",
    "SMTV-T6": "PASS|MANUAL_PENDING",
    "SMTV-T7": "PASS",
    "SMTV-T8": "PASS",
    "live_smoke": "PASS|SKIPPED"
  },
  "evidence": {
    "unit_test_total": 162,
    "onefile_size_mb": 190.8,
    "installer_size_mb": 137.2,
    "smoke_e2e_onefile": "3 passed in <2.5min, SRT + JSON with --> arrows",
    "smoke_e2e_installer": "1 passed in <2min from C:\\Temp\\installed_test"
  }
}
```
