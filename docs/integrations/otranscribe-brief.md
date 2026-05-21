# oTranscribe Integration — Implementation Brief

Self-contained brief for a fresh Claude Code session acting as the **third architect**. Phase 0 (correctness baseline + docs) and Phase 1a (theme + platformdirs + logging) are already on `origin/master`. Your scope is bidirectional file-format compatibility with [oTranscribe](https://otranscribe.com/).

**Read `docs/integrations/otranscribe-research.md` first.** It is the canonical reference for the `.otr` format spec, timestamp HTML structure, and design rationale. This brief is the *what*; the research note is the *why* and the *details*.

---

## Where we are right now

| Phase | Last commit on `origin/master` | Status |
|---|---|---|
| Phase 0 (baseline + docs + WinError fix) | `50a4fea` | merged, verified |
| Phase 1a / sv-ttk theme | `376141a` | merged, verified |
| Phase 1a / logging | `a73710f` | merged, verified |
| Phase 1a / platformdirs | `e9e44a7` | merged, verified |
| Phase 1a / requirements | `3a5f1d0` | merged, verified |
| Phase 1 brief revision (hands-off) | `283b7c6` | merged |

Phase 1 acceptance plan is in `docs/PHASE_1_ACCEPTANCE.md`. **Re-run all of it after your changes** — your work must not break it.

---

## Hands-off policy

You implement, test, commit, push. The user does not babysit. When Phase 0 + Phase 1 + Phase 2-oTranscribe acceptance reports all return `"ACCEPTED"`, push automatically to `origin/master` and emit the final combined JSON report.

If any acceptance is `"REJECTED"` after **three iteration attempts on the same failing test**, stop, do not push partial work, emit the failure report with evidence.

Use the host credential helper for push. Never embed a GitHub token in a URL, commit, or file. Stay on `master` — no branches, no rebases, no force pushes.

---

## Scope

### 1. Core library — `core/integrations/otranscribe.py`

Three pure public functions plus one helper. Stdlib only (`json`, `html`, `html.parser`, `re`, `pathlib`).

```python
def fmt_otr_time(seconds: float) -> str:
    """oTranscribe display format. Less than one hour: 'M:SS'. One hour or more: 'H:MM:SS'.
    No zero-padding on the hour, two-digit minutes and seconds. Match src/js/app/timestamps.js."""

def srt_to_otr(srt_path: str, media_filename: str = "") -> str:
    """Read an SRT file, return the .otr JSON as a string (UTF-8, ensure_ascii=False)."""

def whisper_json_to_otr(json_path: str, media_filename: str = "") -> str:
    """Read our app's JSON output (a list of {start, end, text}), return the .otr JSON.
    Same output schema as srt_to_otr."""

def otr_to_srt(otr_path: str) -> str:
    """Read an .otr file, return SRT text.
    End times: inferred from the next segment's start. The last segment's end time is
    max(media_time, start + 5.0) so it doesn't collapse to zero duration."""
```

Public API surface — exactly these four names. No other public symbols. Internals (the HTMLParser subclass, helpers) are module-private.

### 2. UI changes — `gui.py`

Three small additions:

- **Transcription Queue tab, right-click on a `finished` task:**
  - `Export → oTranscribe (.otr)` — writes `<base>.otr` alongside the existing `<base>.srt`. Show a status-bar message: `Saved <base>.otr`.
- **Transcribe tab, after the existing controls:**
  - A button `Import .otr → SRT...` opens `filedialog.askopenfilename`, then `filedialog.asksaveasfilename` for the output, then runs `otr_to_srt` and writes UTF-8.
- **Help menu (already exists for `Open log folder`):**
  - Add `Open oTranscribe...` that calls `webbrowser.open("https://otranscribe.com/")`.

Wire everything through `core/integrations/otranscribe`. The UI handlers should be small wrappers (10 lines each).

### 3. Tests — `tests/integrations/test_otranscribe.py`

Create `tests/__init__.py` and `tests/integrations/__init__.py` (both empty).

| Test | What it asserts |
|---|---|
| `test_fmt_otr_time` | `fmt_otr_time(3.456)` == `"0:03"`; `fmt_otr_time(63)` == `"1:03"`; `fmt_otr_time(3723)` == `"1:02:03"`; `fmt_otr_time(0)` == `"0:00"` |
| `test_srt_to_otr_smoke` | Convert a 4-segment ASCII SRT fixture; parse the result with `json.loads`; assert keys `{"text","media","media-source","media-time"}`; assert `text` is a single line (no `\n`); assert four `<span class="timestamp">` substrings present |
| `test_srt_roundtrip_ascii` | SRT → `.otr` → SRT. Number of segments match. Each segment's start time matches within ±0.001 s. Each segment's text matches verbatim. End times may differ (round-trip loses them by design — they're inferred). |
| `test_srt_roundtrip_persian` | Same with `tests/integrations/fixtures/sample_persian.srt`. `ensure_ascii=False` must not garble the Persian. |
| `test_whisper_json_to_otr` | Read `tests/integrations/fixtures/sample_whisper.json` (a list of 3 `{start, end, text}` dicts), convert; assert 3 timestamp spans |
| `test_otr_text_uses_nbsp` | After `srt_to_otr`, the JSON `text` field contains `</span> ` (NBSP) but does NOT contain `</span> ` (regular space) at any segment boundary |
| `test_otr_text_single_line` | The `text` field of the produced JSON contains zero `\n` characters |
| `test_otr_to_srt_last_segment_end` | Build a synthetic `.otr` with one segment at start=10.0, `media-time`=20.0; `otr_to_srt` must produce SRT with end time around 20.0 (within 1 s tolerance) |
| `test_media_field_basename_only` | If caller passes `"C:/path/to/audio.mp3"`, the `media` field is `"audio.mp3"`, not the full path |

Fixtures:

- `tests/integrations/fixtures/sample.srt` — 4 segments, ASCII (e.g. `Welcome to the show.` / `Today we talk about...` / `First topic.` / `Goodbye.`)
- `tests/integrations/fixtures/sample_persian.srt` — 3 segments, mixed Persian/English
- `tests/integrations/fixtures/sample_whisper.json` — 3-element list matching our app's JSON output

### 4. Documentation

- `docs/CHANGELOG.md` Unreleased — `### Added` lines for the library, UI buttons, and tests
- `README.md`:
  - "What sets it apart" — add a one-line bullet: `oTranscribe round-trip — export to .otr for human proofing, import edited .otr back to SRT`
  - "Tabs" section — append a paragraph to "Transcription Queue" describing the right-click Export entry, and one to "Transcribe" describing the Import button
- `docs/ROADMAP.md` — under a new "Completed integrations" heading at the top of the file, link to `docs/integrations/otranscribe-research.md` and to this brief. Mark Phase 2-oTranscribe DONE.
- `docs/integrations/README.md` — append an entry to the index table (this file already exists; see its format)

### 5. Acceptance plan — `docs/integrations/otranscribe-acceptance.md`

Create this file modeled on `docs/PHASE_1_ACCEPTANCE.md`. The same eight-or-more tests as the research/brief proposes, expressed as runnable commands with exact expected output. Include a final mandatory JSON report block.

The verifier (a separate session, or `pytest`) should be able to paste this file's body and get a deterministic pass/fail.

---

## Reference: an actual `.otr` body

Build your `srt_to_otr` to produce JSON exactly like this:

```json
{
  "text": "<p><span class=\"timestamp\" contenteditable=\"false\" data-timestamp=\"0.000\">0:00</span> Welcome to the show.</p><p><span class=\"timestamp\" contenteditable=\"false\" data-timestamp=\"3.456\">0:03</span> Today we talk about transcription.</p>",
  "media": "interview-01.mp3",
  "media-source": "",
  "media-time": 0.0
}
```

When serialized: pretty-printing is fine (oTranscribe ignores whitespace **outside** the `text` string). What matters is that **inside** `text` there are no literal `\n` characters.

For `otr_to_srt`, you must parse `text` back. A canonical implementation:

```python
from html.parser import HTMLParser

class _OtrParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.segments = []   # list of (start_seconds: float, text: str)
        self._current_start = None
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        if tag == "span":
            attrs_dict = dict(attrs)
            if attrs_dict.get("class") == "timestamp":
                # flush any text accumulated for the previous segment
                if self._current_start is not None:
                    self.segments.append((self._current_start, "".join(self._buffer).strip().lstrip(" ").strip()))
                self._current_start = float(attrs_dict["data-timestamp"])
                self._buffer = []

    def handle_endtag(self, tag):
        if tag == "p" and self._current_start is not None:
            # paragraph boundary — same effect as encountering the next span
            self.segments.append((self._current_start, "".join(self._buffer).strip().lstrip(" ").strip()))
            self._current_start = None
            self._buffer = []

    def handle_data(self, data):
        if self._current_start is not None:
            # ignore the timestamp display text itself ("0:03"); accept only data
            # that arrives after the span closes. The HTMLParser delivers the
            # display text BEFORE the span's </span>, so use a flag if needed.
            self._buffer.append(data)
```

Note: HTMLParser emits the timestamp's display text (`"0:03"`) as `handle_data` *inside* the span. You need to ignore data while inside the timestamp span (use a `self._in_timestamp` boolean flipped in `handle_starttag`/`handle_endtag` of `<span class="timestamp">`).

The research note has more discussion of edge cases (multi-paragraph segments, the NBSP, etc.).

---

## Constraints

- **Single branch.** `master`. No new branches, no rebases, no force-push.
- **No new dependencies.** Stdlib only. If you find yourself wanting `beautifulsoup4` or `lxml`, stop — `html.parser` is enough.
- **No tokens in code or commits.** Use host credential helper for push.
- **Don't break Phase 0 or Phase 1.** Re-run both acceptances after your changes; if any test regresses, fix it before pushing.
- **Don't touch the worker subprocess protocol.** This is a pure file-format feature; everything is synchronous Python.
- **Don't ship a vendored copy of oTranscribe.** Tier 3 (local URL preload, in-app editor) is explicitly out of scope. If you finish fast, **don't expand scope** — add a new entry to `docs/ROADMAP.md` for Tier 3 instead.
- **Don't move the research file again.** It now lives at `docs/integrations/otranscribe-research.md`. Update references, don't rename it.

---

## Known traps

1. **Newlines inside `text`.** oTranscribe's own export strips only the first `\n` (a known bug, [issue #93](https://github.com/oTranscribe/oTranscribe/issues/93)). Your output must be a single-line HTML string regardless.
2. **`data-timestamp` is seconds.** Floating point, no millisecond conversion. Sources older than 2020 sometimes say milliseconds — they're wrong. Authoritative file is `src/js/app/timestamps.js` in the oTranscribe repo.
3. **Display text format.** `M:SS` for < 1 hour, `H:MM:SS` for ≥ 1 hour. The hour digit is NOT zero-padded. (See [issue #32](https://github.com/oTranscribe/oTranscribe/issues/32).)
4. **NBSP after the closing `</span>`.** Unicode ` `, written as ` ` in Python strings. Don't use a regular space — round-trip will subtly drift.
5. **Persian / Arabic.** `ensure_ascii=False` on `json.dumps`, write file with `encoding="utf-8"`. The fixture for `test_srt_roundtrip_persian` exists precisely to catch regressions here.
6. **The `.otr` extension on a JSON file.** Do not zip, gzip, or otherwise compress. Just plain JSON with a `.otr` suffix.
7. **HTMLParser emits the span's display text inside `handle_data`.** Track an `_in_timestamp` flag so you skip the `"0:03"` text and only collect the segment body that follows the span's closing tag.
8. **`webbrowser.open` on Windows** opens the user's default browser — fine. Don't try to force a specific browser.
9. **End-time inference.** For all but the last segment, end = next segment's start. For the last, end = `max(media_time, start + 5.0)`. Document this in the function docstring.

---

## Source files in the oTranscribe repo to glance at

If anything in the brief is unclear, these files in https://github.com/oTranscribe/oTranscribe answer most questions:

- `src/js/app/export.js` — how `.otr` is built and what fields it has
- `src/js/app/import.js` — what oTranscribe accepts and how it validates
- `src/js/app/timestamps.js` — the canonical timestamp HTML structure and the `M:SS` / `H:MM:SS` formatting logic
- `src/js/app/clean-html.js` — the HTML sanitizer; useful to understand what tags are preserved

---

## Step 8 — Push and final report

When Phase 0 + Phase 1 + Phase 2-oTranscribe acceptances all return `"overall": "ACCEPTED"`:

```bash
git push origin master
```

Then emit:

```json
{
  "branch": "master",
  "commits_added": ["<sha>", "..."],
  "phase_0": { "overall": "ACCEPTED", "tests": {...} },
  "phase_1a": { "overall": "ACCEPTED", "tests": {...} },
  "phase_2_otranscribe": { "overall": "ACCEPTED", "tests": {...} },
  "push": { "status": "ok", "remote": "origin/master", "head": "<sha>" }
}
```

If anything fails, set `"push": {"status": "skipped_due_to_failure", "reason": "..."}` and emit the failure evidence. Do not retry push more than twice.

After emitting the report, exit. The user does not need to be prompted to push — you already did it.

---

## Pointers

- Format spec, schema, design rationale: `docs/integrations/otranscribe-research.md`
- Phase 0 acceptance to re-run: `docs/PHASE_0_ACCEPTANCE.md`
- Phase 1 acceptance to re-run: `docs/PHASE_1_ACCEPTANCE.md`
- Project README: `README.md`
- Roadmap: `docs/ROADMAP.md`
- Test conventions: there are no other tests yet — you are establishing the pattern. Follow Phase 1's directory layout (`tests/<area>/test_<thing>.py`, fixtures alongside) and pytest's defaults (no `pytest.ini` needed).
