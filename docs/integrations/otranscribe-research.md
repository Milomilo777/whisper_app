# oTranscribe Integration — Research Notes

> **Status:** Research note. The implementation brief that consumes this file is [`otranscribe-brief.md`](otranscribe-brief.md). Both files were authored in advance of Phase 2-oTranscribe so the implementing session can start with a complete spec. Sister index: [`README.md`](README.md).

## Why this exists

The user has historically used [oTranscribe](https://otranscribe.netlify.app/) for human-driven manual transcription. They want our app to interoperate with it, so the workflow can be:

1. Transcribe audio with our app (faster-whisper) → output SRT
2. Open the SRT in oTranscribe for human proofreading / cleanup
3. Save edited transcript back to our app for re-alignment / re-export

Goal: bidirectional file-format converters plus a couple of UI buttons.

## What oTranscribe is

- **Source:** [oTranscribe/oTranscribe](https://github.com/oTranscribe/oTranscribe), MIT-licensed, browser-only HTML/JavaScript
- **No backend, no API, no plugin system.** Interop must go through files
- **Hosted at:** https://otranscribe.com/ (main) and https://otranscribe.netlify.app/ (mirror)
- An abandoned Electron wrapper exists: [OpenNewsLabs/oTranscribe-electron](https://github.com/OpenNewsLabs/oTranscribe-electron)
- A maintained ASR-augmented fork: [projecte-aina/oTranscribe-plus](https://github.com/projecte-aina/oTranscribe-plus) (uses Vosk; not faster-whisper)

## The `.otr` file format

Source of truth: `src/js/app/export.js` in the oTranscribe repo.

`.otr` is a **plain JSON file with the `.otr` extension** (not zipped). Exactly four keys:

```json
{
  "text": "<p><span class=\"timestamp\" contenteditable=\"false\" data-timestamp=\"0.000\">0:00</span> Welcome to the show.</p><p><span class=\"timestamp\" contenteditable=\"false\" data-timestamp=\"3.456\">0:03</span> Today we talk about...</p>",
  "media": "interview-01.mp3",
  "media-source": "",
  "media-time": 123.456
}
```

| Field | Type | Meaning |
|---|---|---|
| `text` | string (HTML) | Editor content. Paragraphs, `<b>`/`<i>`, and timestamp `<span>`s. **Important:** the HTML is on a single line; oTranscribe's export does a `replace('\n', '')` once. Write your HTML without literal newlines. |
| `media` | string | Last media filename. Display only — oTranscribe does **not** load this file path automatically on import. |
| `media-source` | string | Legacy; usually empty |
| `media-time` | number (float, seconds) | Last playback position when saved. Re-restored on import |

### Timestamp span format

```html
<span class="timestamp" contenteditable="false" data-timestamp="123.456">2:03</span>
```

Then immediately followed by a non-breaking space ` ` (U+00A0) before the segment text.

- `data-timestamp` is **seconds (float, three decimal places typically)**
- Display text is `M:SS` for < 1 hour, `H:MM:SS` for ≥ 1 hour, **without zero-padding on the hour**
- Keyboard shortcut in oTranscribe to insert: `Ctrl+J`

### What oTranscribe imports

Only `.otr`. SRT, VTT, plain TXT are **not** accepted — the import handler explicitly rejects them with:

```
This is not a valid oTranscribe format (.otr) file.
```

### What oTranscribe exports

`.otr`, `.txt`, `.md`, and Google Drive. **No SRT/VTT.** A long-open issue ([#10](https://github.com/oTranscribe/oTranscribe/issues/10)) requests SRT round-trip; it has been open since 2014 and is not actively being addressed.

### Related tooling

- [Leftium/otrgen](https://github.com/Leftium/otrgen) — CoffeeScript CLI that converts YouTube SBV/TTML → `.otr`. Source is usable as a reference for our Python converter.
- **No Python library exists.** The PyPI package named `otranscribe` ([ineslino/otranscribe](https://github.com/ineslino/otranscribe)) is an unrelated Whisper wrapper that shares the name by coincidence — it has nothing to do with the oTranscribe web app.

## Integration plan — three tiers

### Tier 1 — MVP (1–2 hours): two file converters

A single module with two pure functions. Zero new dependencies.

**File:** `core/integrations/otranscribe.py`

```python
def srt_to_otr(srt_path: str, media_filename: str = "") -> str:
    """Read an SRT file, return an .otr JSON string."""

def whisper_json_to_otr(json_path: str, media_filename: str = "") -> str:
    """Read our app's JSON output (list of {start, end, text}), return .otr."""

def otr_to_srt(otr_path: str) -> str:
    """Read an .otr file, return SRT text. End times inferred from next start.
    Last segment ends at media-time or start + 5 seconds."""
```

Implementation hints:

- Use `json.dumps(..., ensure_ascii=False)` so Persian/Arabic text round-trips cleanly
- Use Python `html` module's `escape` for segment text inside HTML
- For `otr_to_srt`, parse `text` with `html.parser.HTMLParser`. Walk the DOM: every `<span class="timestamp">` is a segment boundary; the text that follows until the next span (or end of paragraph) is the segment text. Strip the NBSP ` ` that always follows the span.
- Format timestamp display string per oTranscribe convention (`fmt_otr_time(seconds)` → `"0:03"` or `"1:23:45"`)

**File:** `tests/integrations/test_otranscribe.py`

- Round-trip: SRT → `.otr` → SRT. Both SRTs match modulo line-ending normalization.
- Real-world test: read `tests/fixtures/sample.srt` (4–5 segments, ASCII), convert, parse back, assert.
- Persian fixture: 2-3 segments with `پارسی` text, ensure UTF-8 survives.
- Edge case: empty text segments, very long single segments (no internal punctuation).

### Tier 2 — UI buttons (half a day)

Two buttons on the "Transcription Queue" tab, available on a right-click for any `finished` task:

- **"Export to oTranscribe (.otr)"** — runs `srt_to_otr(task.output_srt, task.media_filename)`, writes alongside the SRT.
- **"Import .otr → SRT"** — file picker, runs `otr_to_srt()`, writes the SRT to a chosen folder.

And a third button on the "Transcribe" tab:

- **"Open in oTranscribe"** — after a transcription finishes, opens the user's browser to `https://otranscribe.com/` with a small toast: "Now drag the audio file and the `.otr` next to it into the page." (oTranscribe has no URL parameters; this is the best we can do without forking it.)

### Tier 3 — Power features (a week)

Out of scope for now. Documented for the roadmap:

- **Local fork of oTranscribe with `?audio=…&otr=…` URL params.** Vendor `oTranscribe/` into `vendor/otranscribe/`, patch `src/js/app/init.js` to read URL hash and auto-load. Then the "Open in oTranscribe" button preloads both files from a local HTTP server.
- **In-app editor** — a Tkinter Text widget plus audio playback (pygame or VLC bindings), reproducing oTranscribe's keyboard shortcuts (Esc for play/pause, Ctrl+J for timestamp insert, Ctrl+Shift+,/. for speed).
- **Forced alignment after human edit** — pipe the edited transcript through WhisperX's `wav2vec2` alignment to get word-perfect timestamps back, even after manual rewording.

## Risk and footnote

- The HTML in `.otr`'s `text` field is fragile. Don't pretty-print. Don't include newlines inside it (oTranscribe's import does a non-greedy newline strip that has known bugs).
- oTranscribe doesn't preserve word-level timestamps — only paragraph-level. Round-tripping through it discards that information. If we want to preserve word timestamps for downstream forced alignment, we need to keep our JSON next to the SRT and ignore the `.otr` round-trip for that data.
- `.otr`'s `media-time` field can be used to remember where the user paused. Not useful for our automated round-trip, but consider populating it with `0.000` for clean files.
- The `media` field is a display-only filename. We should populate it with the source media's basename (no path) so oTranscribe shows it as a hint.

## Open questions for the user

- Should "Open in oTranscribe" open the official `otranscribe.com` (online), or should we ship a local vendored copy that works offline? Offline is more in keeping with the project's "fully local" identity but adds ~3 MB to the install and requires keeping the fork in sync.
- Does the user want the `.otr` to be written next to the SRT automatically on every transcription finish, or only on explicit button click?
- Should there be a setting to choose the default oTranscribe output format (e.g. one segment per paragraph vs. one minute per paragraph)?

These can be revisited when the MVP is in front of the user.

## Sources

- [oTranscribe GitHub](https://github.com/oTranscribe/oTranscribe)
- [oTranscribe README](https://github.com/oTranscribe/oTranscribe/blob/master/README.md)
- [Round Trip Transcriptions issue #10](https://github.com/oTranscribe/oTranscribe/issues/10)
- [Timestamp formatting issue #32](https://github.com/oTranscribe/oTranscribe/issues/32)
- [otrgen converter](https://github.com/Leftium/otrgen)
- [oTranscribe-plus fork](https://github.com/projecte-aina/oTranscribe-plus)
