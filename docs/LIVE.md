# Live transcription (the Live tab)

Transcribe a microphone — or whatever this computer is currently playing
— as it happens, instead of recording a file first and transcribing it
afterwards.

Implemented in `core/live.py` (engine, Tk-free),
`app/services/live_service.py` (worker plumbing) and
`app/widgets/live_tab.py` (the tab).

## Using it

1. Open the **Live** tab.
2. Pick a **source**: *Microphone*, or *System audio (what you hear)* for
   a meeting, a video, or a call you are listening to.
3. Pick the **language** if you know it. Auto-detect works, but each
   chunk is only a few seconds long and detection on short audio can
   guess wrong and switch mid-session.
4. **Start listening**. The first start loads the speech model, which
   takes a while; the tab says so.
5. Text appears a few seconds behind the speech (see *Latency* below).
6. **Stop**, then **Save transcript…** or **Copy all**.

The whole session is also written to a WAV under the app's cache folder,
so a live session is never *only* live — the audio survives if you want
to re-transcribe it properly afterwards.

## Requirements

| Source | Needs | Notes |
|---|---|---|
| Microphone | `sounddevice` | Any platform |
| System audio | `PyAudioWPatch` | **Windows only** (WASAPI loopback) |

Neither is bundled. When a backend is missing the source is simply not
offered, and Start explains what to install rather than failing later.

## How it works

```
Recorder (capture thread) --frames--> Segmenter --chunks-->
    bounded queue --worker thread--> live worker subprocess --> events
        --> Tk after() poll --> the transcript widget
```

### Chunks are cut at silence, not on a timer

Slicing the audio every N seconds splits words in half, and half a word
transcribes as either nothing or the wrong word. The segmenter watches
the signal level and closes a chunk **during a pause**.

An utterance that runs on with no pause is force-cut at `max_chunk_s`
(12 s by default) so the transcript keeps moving — and even then the
split prefers the quietest moment in the last second over the exact
deadline, so a forced cut still tends to land between words.

### Silence is never sent to the model

A chunk with no voiced audio is dropped rather than transcribed. Whisper
hallucinates confidently on silence — invented sentences during a quiet
stretch are the single biggest source of junk in a live transcript, and
dropping the chunk costs nothing.

### It says when it falls behind

If transcription is slower than real time (a large model on a weak CPU),
the bounded queue drops the **oldest** pending chunk and counts it. The
status line and the log say so.

Dropping the oldest is deliberate: the newest audio is what the user is
watching for, and letting a backlog grow just drifts further behind with
every chunk. A live transcript that quietly skips audio is worse than one
that admits it — so this is never silent.

If you see that warning, pick a smaller model in **Advanced > Whisper
model**. `large-v3` is not a real-time model on most CPUs; `small`,
`base` or `large-v3-turbo` are far better suited.

### The model lives in its own worker

A live session spawns its **own** `core.worker` subprocess and shuts it
down on Stop.

- Not in the GUI process: `app/` deliberately never imports
  faster-whisper, and an in-process model would put GB in the Tk process
  and freeze the window during every inference.
- Not the `TranscriptionService` pool: a live session and a queued file
  would fight over the same worker and whichever lost would stall.

The cost is a second model resident while a live session runs alongside a
file transcription. The tab says so rather than hiding it.

The worker gained one action for this, `transcribe_live`, which
transcribes a chunk and returns the text inline — writing no files,
taking no checkpoint, and skipping the post-pipeline (diarisation,
alignment, chapters). Running all of that every few seconds for a
6-second chunk would be wasteful, would spray files across the disk, and
with diarisation enabled would make live transcription unusable. The
protocol stays add-only: an older parent that never sends this action is
unaffected.

## Latency

Text lags the speech by roughly:

```
pause detection (~0.5s) + chunk length (2-12s) + inference time
```

This is inherent to chunked recognition. Cutting sooner would mean
cutting mid-word, which costs accuracy for a barely noticeable latency
win. Tuning lives in `core.live.SegmenterConfig`.

## Limitations

- **Not a dictation tool.** Words appear per utterance, not per word.
- **No live translation.** The transcript is in the spoken language.
- **No speaker labels.** Diarisation needs the whole file; use the
  Transcribe tab on the saved WAV for that.
- **System audio is Windows-only** — macOS and Linux have no equivalent
  loopback device without a third-party virtual audio driver.
- Auto-detect can pick the wrong language on short chunks. Name the
  language when you know it.

## Related

- [DENOISE.md](DENOISE.md) — the denoise pre-process applies to file
  transcription, not to live chunks (it needs to measure a whole
  recording first).
- `core/recorder.py` — the capture backends, also usable on their own.
