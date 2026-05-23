# DEBUG_RUNTIME_BASIC — runtime hostile-probe report

Probe date: 2026-05-23

**Summary.** Drove the basic-edition worker through 26 hostile scenarios via `python gui.py --worker` + JSON-on-stdin. Result: **23 PASS / 3 WARN / 0 FAIL**. No worker crash, no orphan files, no hang under any input. Three WARN items are quality-of-implementation issues, not safety bugs: (a) `attrib +R` on a folder is a Windows no-op so the worker happily wrote into a "read-only" folder; (b) `shutdown` sent mid-transcribe is not honoured until the current file finishes — the worker had to be force-killed at the 10 s deadline because the 90 s test clip was still in flight; (c) `hub_folder` pointing at an unmounted drive Z: does NOT fall back to the default hub — it falls back to the same dead drive and emits `startup_error`. See the triage list at the bottom.


## 1. 0-byte file

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\empty.mp3"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\empty.mp3", "event": "started"}`
  - `{"message": "ffmpeg/ffprobe could not read the media file.", "suggestion": "Make sure the file is a real audio/video file and not corrupt. Try playing it in VLC first.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\empty.mp3", "event": "error"}`
  - (totals: {'log': 2, 'ready': 1, 'started': 1, 'error': 1})

**Final event:** `{"message": "ffmpeg/ffprobe could not read the media file.", "suggestion": "Make sure the file is a real audio/video file and not corrupt. Try playing it in VLC first.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\empty.mp3", "event": "error"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — clean error event

## 2. Garbage text renamed .mp3

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\text.mp3"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\text.mp3", "event": "started"}`
  - `{"message": "ffmpeg/ffprobe could not read the media file.", "suggestion": "Make sure the file is a real audio/video file and not corrupt. Try playing it in VLC first.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\text.mp3", "event": "error"}`
  - (totals: {'log': 2, 'ready': 1, 'started': 1, 'error': 1})

**Final event:** `{"message": "ffmpeg/ffprobe could not read the media file.", "suggestion": "Make sure the file is a real audio/video file and not corrupt. Try playing it in VLC first.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\text.mp3", "event": "error"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — ffprobe/decoder error surfaced cleanly

## 3. Truncated 4KB file

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\truncated.mp3"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\truncated.mp3", "event": "started"}`
  - `{"message": "ffmpeg/ffprobe could not read the media file.", "suggestion": "Make sure the file is a real audio/video file and not corrupt. Try playing it in VLC first.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\truncated.mp3", "event": "error"}`
  - (totals: {'log': 2, 'ready': 1, 'started': 1, 'error': 1})

**Final event:** `{"message": "ffmpeg/ffprobe could not read the media file.", "suggestion": "Make sure the file is a real audio/video file and not corrupt. Try playing it in VLC first.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\truncated.mp3", "event": "error"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — finished cleanly as error

## 4. Unicode path (CJK + emoji)

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\\u6d4b\u8bd5 \u4e2d\u6587 \ud83c\udfb5\\clip.mp3"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\\u6d4b\u8bd5 \u4e2d\u6587 \ud83c\udfb5\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\\u6d4b\u8bd5 \u4e2d\u6587 \ud83c\udfb5\\clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\\u6d4b\u8bd5 \u4e2d\u6587 \ud83c\udfb5\\clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\\u6d4b\u8bd5 \u4e2d\u6587 \ud83c\udfb5\\clip.mp3", "event": "done"}`
  - (totals: {'log': 15, 'ready': 1, 'started': 1, 'heartbeat': 20, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\\u6d4b\u8bd5 \u4e2d\u6587 \ud83c\udfb5\\clip.mp3", "event": "done"}`

**Output files present:** 3/3

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — done; wrote 3/3 outputs

## 5. Spaces + quotes + brackets in name

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\o''ut [s p a c e s] (paren).mp3"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\o''ut [s p a c e s] (paren).mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\o''ut [s p a c e s] (paren).mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\o''ut [s p a c e s] (paren).mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\o''ut [s p a c e s] (paren).mp3", "event": "done"}`
  - (totals: {'log': 15, 'ready': 1, 'started': 1, 'heartbeat': 20, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\o''ut [s p a c e s] (paren).mp3", "event": "done"}`

**Output files present:** 3/3

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — done; wrote 3/3

## 6. Very long path (>260 chars)

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\long\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\clip.mp3", "path_len": 295}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\long\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\long\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_p`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\long\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_na`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\long\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup`
  - (totals: {'log': 15, 'ready': 1, 'started': 1, 'heartbeat': 20, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\long\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup\\long_segment_name_for_path_blowup`

**Output files present:** 3/3

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — done; wrote 3/3 outputs at len=295

## 7. Read-only output folder (attrib +R)

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\readonly\\clip.mp3"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\readonly\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\readonly\\clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\readonly\\clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\readonly\\clip.mp3", "event": "done"}`
  - (totals: {'log': 15, 'ready': 1, 'started': 1, 'heartbeat': 20, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\readonly\\clip.mp3", "event": "done"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: WARN** — wrote into 'read-only' folder (Windows attrib +R is a no-op for folders)

## 8. Symlink to real file

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\link_clip.mp3"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\link_clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\link_clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\link_clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\link_clip.mp3", "event": "done"}`
  - (totals: {'log': 15, 'ready': 1, 'started': 1, 'heartbeat': 20, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\link_clip.mp3", "event": "done"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — followed symlink and transcribed

## 9. File deleted mid-flight

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ephemeral_clip.mp3", "then": "unlink in sibling thread"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ephemeral_clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ephemeral_clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ephemeral_clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ephemeral_clip.mp3", "event": "done"}`
  - (totals: {'log': 15, 'ready': 1, 'started': 1, 'heartbeat': 20, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ephemeral_clip.mp3", "event": "done"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — finished cleanly as done

## 10. Invalid JSON on stdin

**Sent.** `not json at all\n then a real transcribe`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"message": "Invalid worker command: Expecting value: line 1 column 1 (char 0)", "event": "error"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`
  - (totals: {'log': 15, 'ready': 1, 'error': 1, 'started': 1, 'heartbeat': 20, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — logged error and continued; subsequent transcribe completed

## 11. Oversize JSON line (2 MB)

**Sent.** `2 MB JSON line then a real transcribe`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"message": "command exceeds max length (> 1048576 bytes); dropped", "event": "error"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`
  - (totals: {'log': 15, 'heartbeat': 25, 'ready': 1, 'error': 1, 'started': 1, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — rejected oversize line and continued

## 12. Unknown action

**Sent.** `{"action": "what_is_this"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"message": "Unknown worker command: what_is_this", "event": "error"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`
  - (totals: {'log': 15, 'heartbeat': 25, 'ready': 1, 'error': 1, 'started': 1, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — unknown action rejected (Unknown worker command: what_is_this)

## 13. Missing required field

**Sent.** `{"action": "transcribe"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"message": "Missing input file", "event": "error"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`
  - (totals: {'log': 15, 'heartbeat': 23, 'ready': 1, 'error': 1, 'started': 1, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — missing field rejected: Missing input file

## 14. Two transcribes back-to-back

**Sent.** `two {action:transcribe} lines 50ms apart`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\b2b_1.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\b2b_1.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\b2b_1.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\b2b_1.mp3", "event": "done"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\b2b_2.mp3", "event": "started"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\b2b_2.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\b2b_2.mp3", "event": "done"}`
  - (totals: {'log': 28, 'heartbeat': 44, 'ready': 1, 'started': 2, 'language_detected': 2, 'progress': 22, 'done': 2})

**Done set:** ['C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\b2b_1.mp3', 'C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\b2b_2.mp3']
**Started count:** 2

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — both files processed serially (started_count=2)

## 15. Shutdown mid-transcribe

**Sent.** `transcribe, wait 5s, shutdown`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "log"}`
  - (totals: {'log': 3, 'heartbeat': 5, 'ready': 1, 'started': 1})

**Exit code:** `1`  **Killed:** `True`

**Verdict: WARN** — worker had to be force-killed (didn't honour shutdown)

## 16. SIGKILL mid-transcribe

**Sent.** `transcribe then taskkill /F after 5s`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "log"}`
  - (totals: {'log': 3, 'heartbeat': 3, 'ready': 1, 'started': 1})

**Model-dir diff:** `{'added': [], 'removed': []}`
**Stray .part files:** `[]`

**Exit code:** `1`  **Killed:** `True`

**Verdict: PASS** — no half-written model files, no orphan .part files in PROBE

## 17. Two workers same model dir

**Sent.** `two parallel transcribes on two workers, same MODEL_DIR`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\w1\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\w1\\clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\w1\\clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\w1\\clip.mp3", "event": "done"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\w2\\clip.mp3", "event": "started"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\w2\\clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\w2\\clip.mp3", "event": "done"}`
  - (totals: {'log': 30, 'heartbeat': 76, 'ready': 2, 'started': 2, 'language_detected': 2, 'progress': 22, 'done': 2})

**Exit code:** `[0, 0]`  **Killed:** `False`

**Stderr (first 600 chars):**
```
--- w1 ---

--- w2 ---
```

**Verdict: PASS** — both workers transcribed independently; shut down cleanly

## 18. Spawn with no model on disk

**Sent.** `config.json with hub_folder→empty dir`

**Emitted (noise stripped):**
  - `{"message": "Model folder missing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\fake_empty_hub\\models--Systran--faster-whisper-large-v3", "event": "log"}`
  - `{"message": "Model folder missing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\fake_empty_hub\\models--Systran--faster-whisper-large-v3", "event": "startup_error"}`
  - (totals: {'log': 1, 'startup_error': 1})

**Startup event:** `{"message": "Model folder missing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\fake_empty_hub\\models--Systran--faster-whisper-large-v3", "event": "startup_error"}`

**Exit code:** `1`  **Killed:** `False`

**Verdict: PASS** — emitted startup_error and exited 1: Model folder missing: C:\Users\Owner\AppData\Local\Temp\wpb_probe\fake_empty_hub\models--Systran--faster-whisper-large-v3

## 19. Heartbeats during 30s idle

**Sent.** `no commands, just observe`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - (totals: {'log': 2, 'heartbeat': 8, 'ready': 1})

**Heartbeats observed:** 8
**Heartbeat intervals (s):** [5.001, 5.001, 5.0, 5.0, 5.0, 5.001, 5.0]

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — got 8 heartbeats in 30s, intervals ~5s ([5.001032114028931, 5.001056432723999, 5.000368595123291, 5.000260353088379, 5.000414848327637])

## 20. Pre-existing read-only .srt

**Sent.** `transcribe C:\Users\Owner\AppData\Local\Temp\wpb_probe\ro_out\short_test.mp3 with pre-existing read-only .srt`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ro_out\\short_test.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ro_out\\short_test.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ro_out\\short_test.mp3", "event": "language_detected"}`
  - `{"message": "Could not write the subtitle file \u2014 it is open in another program.", "suggestion": "Close any media player or text editor showing the output file and try again.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ro_out\\short_test.mp3", "event": `
  - (totals: {'log': 13, 'heartbeat': 21, 'ready': 1, 'started': 1, 'language_detected': 1, 'progress': 10, 'error': 1})

**Final event:** `{"message": "Could not write the subtitle file \u2014 it is open in another program.", "suggestion": "Close any media player or text editor showing the output file and try again.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ro_out\\short_test.mp3", "event": `

**Exit code:** `0`  **Killed:** `False`

**Stderr (first 600 chars):**
```
2026-05-23 20:19:36,839 ERROR core.transcriber � Failed to write srt output
Traceback (most recent call last):
  File "C:\Users\Owner\Desktop\whisper-project-basic\core\transcriber.py", line 272, in _write_outputs
    os.replace(part_path, path)
    ~~~~~~~~~~^^^^^^^^^^^^^^^^^
PermissionError: [WinError 5] Access is denied: 'C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ro_out\\short_test.srt.9424-15664-c5530fe4.part' -> 'C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ro_out\\short_test.srt'
```

**Verdict: PASS** — clean error surfaced: 'Could not write the subtitle file — it is open in another program.'

## 21. Windows-reserved chars in filename

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\bad<>|name.mp3"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\bad<>|name.mp3", "event": "started"}`
  - `{"message": "ffmpeg/ffprobe could not read the media file.", "suggestion": "Make sure the file is a real audio/video file and not corrupt. Try playing it in VLC first.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\bad<>|name.mp3", "event": "error"}`
  - (totals: {'log': 2, 'heartbeat': 1, 'ready': 1, 'started': 1, 'error': 1})

**Final event:** `{"message": "ffmpeg/ffprobe could not read the media file.", "suggestion": "Make sure the file is a real audio/video file and not corrupt. Try playing it in VLC first.", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\bad<>|name.mp3", "event": "error"}`

**Create error:** `[WinError 123] The filename, directory name, or volume label syntax is incorrect`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — could not create file (OS rejected name: [WinError 123] The filename, directory name, or volume label syntax is incorrect); worker reported error: 'ffmpeg/ffprobe could not read the media file.'

## 22. True silence → zero segments

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\silence.wav"}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\silence.wav", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\silence.wav", "event": "log"}`
  - `{"language": "nn", "probability": 0.6893429160118103, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\silence.wav", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\silence.wav", "event": "done"}`
  - (totals: {'log': 5, 'heartbeat': 5, 'ready': 1, 'started': 1, 'language_detected': 1, 'progress': 1, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\silence.wav", "event": "done"}`

**Output sizes:** `{"srt_bytes": 0, "txt_bytes": 1, "json_valid": true, "srt_head": "", "txt_head": "\n"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — done; outputs valid (srt 0B, txt 1B, json valid)

## 23. config.json with wrong type (model_path: 42)

**Sent.** `config.json with model_path=42`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - (totals: {'log': 2, 'heartbeat': 1, 'ready': 1})

**Startup event:** `{"event": "ready"}`

**Exit code:** `0`  **Killed:** `False`

**Stderr (first 600 chars):**
```
config key 'model_path' has wrong type int (expected str); reverting to default
config key 'model_path' has wrong type int (expected str); reverting to default
```

**Verdict: PASS** — worker survived bad config (model_path=42); came up as ready

## 24. hub_folder → unmounted drive (Z:)

**Sent.** `config.json with hub_folder=Z:\nonexistent_hub`

**Emitted (noise stripped):**
  - `{"message": "Model folder missing: Z:\\nonexistent_hub\\models--Systran--faster-whisper-large-v3", "event": "log"}`
  - `{"message": "Model folder missing: Z:\\nonexistent_hub\\models--Systran--faster-whisper-large-v3", "event": "startup_error"}`
  - (totals: {'log': 1, 'startup_error': 1})

**Startup event:** `{"message": "Model folder missing: Z:\\nonexistent_hub\\models--Systran--faster-whisper-large-v3", "event": "startup_error"}`

**Exit code:** `1`  **Killed:** `False`

**Stderr (first 600 chars):**
```
model_path 'Z:\\nonexistent_hub\\models--Systran--faster-whisper-large-v3' is unreachable; using fallback Z:\nonexistent_hub\models--Systran--faster-whisper-large-v3
model_path 'Z:\\nonexistent_hub\\models--Systran--faster-whisper-large-v3' is unreachable; using fallback Z:\nonexistent_hub\models--Systran--faster-whisper-large-v3
```

**Verdict: WARN** — startup_error: 'Model folder missing: Z:\\nonexistent_hub\\models--Systran--faster-whisper-large-v3' (expected fallback to default hub but got error)

## 25. Leading/trailing whitespace in filename

**Sent.** `{"action": "transcribe", "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ws\\  spaces.mp3  "}`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ws\\  spaces.mp3  ", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ws\\  spaces.mp3  ", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ws\\  spaces.mp3  ", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ws\\  spaces.mp3  ", "event": "done"}`
  - (totals: {'log': 15, 'heartbeat': 21, 'ready': 1, 'started': 1, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\ws\\  spaces.mp3  ", "event": "done"}`

**NTFS stored as:** `['  spaces.mp3']`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — done; NTFS stored as ['  spaces.mp3'], transcribe succeeded

## 26. Fuzz: 3x 1 KB random printable lines

**Sent.** `three 1024-byte random lines, then a real transcribe`

**Emitted (noise stripped):**
  - `{"message": "Loading Whisper model...", "event": "log"}`
  - `{"message": "Model loaded", "event": "log"}`
  - `{"event": "ready"}`
  - `{"message": "Invalid worker command: Expecting value: line 1 column 1 (char 0)", "event": "error"}`
  - `{"message": "Invalid worker command: Extra data: line 1 column 2 (char 1)", "event": "error"}`
  - `{"message": "Invalid worker command: Extra data: line 1 column 3 (char 2)", "event": "error"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "started"}`
  - `{"message": "Processing: C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "log"}`
  - `{"language": "en", "probability": 0.9929855465888977, "file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "language_detected"}`
  - `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`
  - (totals: {'log': 15, 'heartbeat': 33, 'ready': 1, 'error': 3, 'started': 1, 'language_detected': 1, 'progress': 11, 'done': 1})

**Final event:** `{"file_path": "C:\\Users\\Owner\\AppData\\Local\\Temp\\wpb_probe\\clip.mp3", "event": "done"}`

**Exit code:** `0`  **Killed:** `False`

**Verdict: PASS** — rejected 3 fuzz blobs as errors, then transcribed cleanly (err_count=3)

---

## Triage — WARN items, ranked

### #1 — Scenario 15: Shutdown not honoured while transcribe in flight

**Severity:** Medium

The worker's main loop uses `for line in sys.stdin:` and calls `transcribe()` synchronously inside the loop. While a transcribe is running, additional stdin lines wait in the OS pipe buffer and are NOT processed until the current transcribe returns. A user clicking "Stop" / closing the app mid-file therefore sees no response for up to the file's full duration; on long files this looks like a hang. Mitigation options: (a) document that the parent should set `task.cancelled = True` AND close stdin to force the worker to drain on the next segment boundary, then exit on EOF; (b) move command parsing onto a daemon thread that can flip a `_shutting_down` flag the transcribe loop polls; (c) leave as-is and ensure the parent always force-kills after a reasonable grace period (this is what my driver had to do at the 10 s deadline).

### #2 — Scenario 24: `hub_folder` on an unmounted drive does NOT fall back

**Severity:** Medium

When `model_path` lives on an unmounted drive, `_apply_runtime_fallbacks` correctly detects that and recomputes a fallback path — but it does so via `effective_hub = hub_folder or default_hub_folder()`, which keeps the user-configured `hub_folder` even when that hub is itself on the dead drive. Result: the "fallback" lands back on `Z:\nonexistent_hub\…`, the worker logs "using fallback Z:\…", and `startup_error` fires anyway. Fix: also probe `hub_folder` with `_drive_is_mounted` and reach for `default_hub_folder()` when the hub is unreachable.

### #3 — Scenario 7: `attrib +R` on the output folder is silently ignored

**Severity:** Low / informational

Windows behaviour — `attrib +R <folder>` does NOT prevent file creation inside the folder; the flag is interpreted by Explorer as "customised folder" and is a no-op for the file system. The worker therefore wrote the .srt/.json/.txt outputs into the folder without issue. To actually test write-protection on Windows you have to set an ACL Deny entry via `icacls`. Not a worker bug, but worth documenting if the spec implies `attrib +R` should block writes. The companion test #20 (read-only .srt file, which IS honoured by the OS) does surface a clean error from the writer.

## Notable PASS items worth highlighting

- **Scenario 16 (SIGKILL mid-transcribe):** after `taskkill /F /T`, the model directory was byte-identical to the pre-kill snapshot and zero `.part` files leaked into the working dir — the atomic `.part`→`os.replace` pattern in `_write_outputs` holds up.
- **Scenario 11 (2 MB JSON line):** the `MAX_COMMAND_BYTES = 1 << 20` cap fired exactly as documented and the worker stayed responsive to a subsequent real transcribe.
- **Scenario 17 (two workers, same model dir):** both workers loaded the model independently, transcribed in parallel, and shut down cleanly — no file lock contention surfaced.
- **Scenario 19 (heartbeats):** 8 heartbeats in 30 s of idle, intervals all within 5.000–5.001 s of each other — solid.
- **Scenario 22 (true silence):** zero-segment audio produces a valid 0-byte .srt, a 1-byte .txt (just newline), and a structurally valid JSON. No crash, no malformed output.

## Methodology note

All 26 scenarios were driven by a Python harness that spawns a fresh worker per scenario (~25 s model-load each), feeds JSON on stdin, reads JSON-line events off stdout via a daemon thread, captures stderr separately, and asserts on the final state. Every scenario ended with `{"action": "shutdown"}`; only scenario 15 hit the 10 s grace-then-`taskkill` path. Real test clip: 90 s English MP3 (~4.6 MB). Total wall-clock: ~38 min. Harness lives at `C:\Users\Owner\AppData\Local\Temp\wpb_probe\` (driver.py + run_all.py + results.json).
