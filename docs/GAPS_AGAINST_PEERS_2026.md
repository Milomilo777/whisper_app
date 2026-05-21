# Gaps against peer products (May 2026)

> **Companion to:** [COMPETITIVE_ANALYSIS_2026.md](COMPETITIVE_ANALYSIS_2026.md)
> — that file is the *ecosystem* survey (ASR models, cloud APIs, ZH/JA
> specifics). This file is the *product* gap analysis: feature-by-
> feature, what comparable desktop apps do that **we** do not.
>
> Scope: Windows desktop. Peers chosen as the closest like-for-like:
>
> - **MacWhisper** (Jordi Bruin) — macOS file transcription + AI
> - **Buzz** (chidiwilliams/buzz) — open-source, Win/macOS/Linux,
>   Whisper-multi-backend
> - **Vibe** (thewh1teagle/vibe) — open-source Tauri, Win/macOS/Linux
> - **Superwhisper / Wispr Flow** — system-wide dictation overlays
> - **Descript** — transcript-driven media editor (cloud, but UX leader)
> - **WhisperX / WhisperKit / Insanely-Fast-Whisper** — alignment +
>   speed reference implementations
>
> Rating: 🟢 we have it · 🟡 partially / behind · 🔴 missing.
> Effort: XS (≤1 day) · S (≤3 days) · M (1–2 weeks) · L (2–4 weeks) · XL (>4 weeks).

---

## A. Core ASR features

| Feature | Us | Peers | Effort to close | Notes |
|---|---|---|---|---|
| **Speaker diarization** (who said what) | 🔴 absent | MacWhisper (beta), Buzz, WhisperX, Descript, Otter | L | The single most-asked feature in transcript tools today. `pyannote.audio` 3.x is the standard local stack. |
| **Word-level ±50 ms alignment** | 🟡 Whisper-native timestamps (drift up to ±500 ms) | WhisperX, stable-ts, MacWhisper, Vibe | M | Pre-requisite for click-to-jump editor. `stable-ts` is the cheapest drop-in. |
| **Live mic transcription** | 🔴 absent | Buzz (live), MacWhisper (recording), Vibe | L | Whisper-Streaming's LocalAgreement-n is the proven pattern. Unlocks dictation use case. |
| **System-wide dictation hotkey** | 🔴 absent | Superwhisper, Wispr Flow, MacWhisper, Handy, VoiceTypr | XL | Out-of-process hotkey + active-window-aware text insertion. The fastest-growing category in 2025/2026. |
| **Multiple Whisper sizes selectable from UI** | 🟡 hard-coded `large-v3` | Buzz, MacWhisper, Vibe (model picker dropdown) | S | We only ship `faster-whisper-large-v3`. Users wanting `tiny`/`base`/`medium` for speed must edit `config.json`. |
| **GPU vs CPU choice exposed in UI** | 🟡 auto-detected, not surfaced | Buzz (Vulkan/CUDA dropdown), MacWhisper | S | Auto-detection is fine but power users want a forced override toggle. |
| **Alternative backends** (whisper.cpp, MLX, NeMo Parakeet) | 🔴 absent — faster-whisper only | Buzz (4 backends), Vibe (whisper-rs), MacWhisper (Whisper + Parakeet + cloud routing) | L | Single backend means single point of failure for new optimisations and for Chinese (where SenseVoice wins). |
| **Custom hot-words / phrase biasing** | 🟡 `initial_prompt`/`hotwords` exist in config, no UI | Deepgram, Azure, ElevenLabs, MacWhisper, CapsWriter | S | Need a per-project glossary editor in the app. |
| **Language picker per-file** | 🟡 set in config, not per-task | Buzz, MacWhisper, Vibe (dropdown next to each task) | S | We use `language` per task internally but the UI never surfaces it. |
| **Translation (target ≠ source)** | 🔴 absent | MacWhisper, Buzz, Descript, Canary-1B-v2 backend | M | Whisper itself supports translation-to-English via `task="translate"`. We never expose this. |
| **Voice/track separation before transcribe** | 🔴 absent | Buzz (Demucs option), Krisp | M | "Remove background music before transcribing" is increasingly expected for podcast/film content. |
| **PII / entity redaction** | 🔴 absent | AssemblyAI, ElevenLabs Scribe v2, Otter | M | Healthcare/legal users need "bleep card numbers" + entity timestamps. |
| **Sound-event tags** (`[Music]`, `[Applause]`) | 🔴 absent | ElevenLabs Scribe v2, SenseVoice (AED) | M | Required for SDH-compliant subtitles. |
| **Cancel mid-transcription** | 🟢 yes | 🟢 all | — | Done. |
| **Auto-resume after crash** | 🟡 SQLite history marks interrupted rows but does not re-queue | MacWhisper (auto-resume), Buzz | S | We have the data, just need a "resume interrupted" prompt at startup. |

---

## B. Editor / playback / transcript viewing

| Feature | Us | Peers | Effort | Notes |
|---|---|---|---|---|
| **In-app transcript viewer** | 🔴 absent — user opens the SRT in Notepad / oTranscribe | Descript, MacWhisper, Buzz, Vibe | M | Our only "viewer" is the black/lime console that scrolls per-segment progress lines and discards them. |
| **Click-word → seek audio/video** | 🔴 absent | Descript (the killer feature), MacWhisper, Buzz | M | Requires word-level alignment + an embedded media player. |
| **Inline transcript editing** | 🔴 absent | Descript, MacWhisper, Buzz | L | Edit the transcript text and re-export to SRT/VTT/TXT without redoing the ASR. |
| **Karaoke-style word highlight during playback** | 🔴 absent | Descript, MacWhisper, Buzz | M | Pure UI on top of word timings. |
| **Search inside transcripts** | 🔴 absent | Otter, Descript, MacWhisper | S | Cmd+F across the active transcript and across the history database. |
| **Speaker rename (global)** | 🔴 absent (no speakers) | Descript, MacWhisper, Otter | S | Falls out of A-speaker-diarization. |
| **Filler-word remove** ("uh"/"um" bulk delete) | 🔴 absent | Descript, Riverside, CapCut | S | Multilingual list per language. |
| **Find-and-replace across transcript** | 🔴 absent | Descript, MacWhisper, Buzz | S | Important for fixing recurring proper-name mistranscriptions. |
| **Embed media player** (audio waveform / video frame) | 🔴 absent | Descript, MacWhisper, Buzz, Vibe | M | Tk has no native media widget; would need `python-vlc`, `pygame`, or HTML+webview switch. |
| **Word-confidence colour coding** | 🔴 absent | Descript, ElevenLabs | S | We have probabilities per word in our JSON — just never shown. |

---

## C. Output / export

| Feature | Us | Peers | Effort | Notes |
|---|---|---|---|---|
| **SRT / VTT / TSV / TXT / LRC / JSON** | 🟢 6 formats | Buzz 3, MacWhisper 5, Vibe 4 | — | **We're ahead here.** |
| **DOCX export** | 🔴 absent | MacWhisper (DOCX), Buzz (DOCX), Otter | S | `python-docx` adds ~1 MB to the bundle. Important for journalists / interview workflows. |
| **PDF export** | 🔴 absent | MacWhisper, Descript | S | `reportlab` or `weasyprint`; same audience as DOCX. |
| **Markdown export** | 🔴 absent | Descript | XS | One writer module, trivial. |
| **SCC / EBU-STL** (broadcast caption formats) | 🔴 absent | Descript, EZTitles | M | Niche but high-value for TV/news clients. |
| **Burn subtitles into the video** | 🔴 absent | MacWhisper, Descript, CapCut | M | `ffmpeg -vf subtitles=…` — we already ship ffmpeg. |
| **Per-format batch export from one transcript** | 🔴 absent | MacWhisper ("export TXT + SRT + DOCX in one click") | S | Currently the config picks one set; per-export-action override would be friendlier. |
| **Output filename templating** | 🔴 absent | MacWhisper, Buzz | S | `{filename}_{lang}_{date}.srt` style. Right now we hard-code `<base>.<ext>` next to the source. |
| **Output directory templating** | 🔴 hard-coded (next to source) | MacWhisper, Buzz | S | "Save all outputs to a single folder" is a common request. |

---

## D. Workflow / ingestion

| Feature | Us | Peers | Effort | Notes |
|---|---|---|---|---|
| **Drag-and-drop into the window** | 🔴 absent | Buzz, MacWhisper, Vibe, Descript | XS | `tkinterdnd2` is on the optional-deps list already; ~200 KB. |
| **Batch queue of dozens of files in one go** | 🟡 we queue, but the Transcribe tab is single-file picker | MacWhisper batch exporter, Buzz, Vibe | S | Need a multi-select in the Browse dialog + drag-drop. |
| **Watched folders** ("transcribe everything I drop into `D:\inbox\`") | 🔴 absent | MacWhisper, Buzz | M | `watchdog` library; existed on the optional-deps list. |
| **YouTube URL ingestion on the Transcribe tab** | 🟡 only via the Download tab + auto-transcribe checkbox | MacWhisper (paste YouTube URL anywhere), Vibe | S | Detect URLs in the file-picker entry, route through the download path. |
| **Right-click "Transcribe this" in Explorer / Finder** | 🔴 absent | MacWhisper (Services menu), VLC + plugin | M | Requires an installer post-action to register a shell extension. |
| **CLI mode** (`WhisperProject.exe transcribe a.mp4`) | 🔴 absent — only `--worker` flag exists | Buzz (`buzz-captions transcribe …`) | S | Power users want scripting. |
| **Per-project / per-folder settings** | 🔴 single global config | MacWhisper (per-folder rules) | M | "Folder X always uses language=fa and word_timestamps=true." |
| **Recent files menu** | 🔴 absent | every comparable app | XS | We already have a SQLite history; surface its last N rows in the File menu. |

---

## E. UI / presentation

| Feature | Us | Peers | Effort | Notes |
|---|---|---|---|---|
| **System tray icon + minimise-to-tray** | 🔴 absent | Superwhisper, Wispr Flow, Handy, VoiceTypr | S | Especially valuable once we add live-dictation. |
| **Windows toast notification on completion** | 🟡 system bell only (after the v0.7.0 UX refresh) | MacWhisper (NSUserNotification), Buzz | S | `win10toast`-style native toast on top of the bell would survive a minimised window. |
| **Internationalised UI** | 🟢 English-only **by design** | MacWhisper (multiple), Buzz | — | Scope choice: this app targets English-speaking users. Multi-language UI is explicitly out of scope. The SMTV scraper accepts non-English URLs but the UI labels stay English. |
| **RTL layout support** | 🟢 not applicable (English-only) | Most modern Qt/Electron apps | — | Out of scope by the same scope choice above. |
| **Dark / light theme** | 🟢 yes (sv-ttk) | 🟢 most | — | Done. |
| **High-DPI scaling** | 🟡 implicit Tk default | MacWhisper, modern Qt apps | S | Tk needs `tk scaling` set explicitly for 150%+ Windows displays. |
| **Resizable / dockable result panel** | 🟡 fixed in our Last Result card | Descript, Buzz | S | Power users want to make the transcript pane huge. |
| **Window state persistence** (remember size / position) | 🔴 absent | every modern desktop app | XS | Save/restore `geometry()`. |
| **Keyboard shortcuts** (Ctrl+O Browse, Ctrl+Enter Transcribe, Esc cancel) | 🔴 absent | Buzz, MacWhisper | XS | Tk bindings, low cost. |
| **Accessibility / screen reader** | 🔴 untested | Apple-first apps inherit it | L | Tk accessibility on Windows is weak; UIA is partial. |

---

## F. Distribution and trust

| Feature | Us | Peers | Effort | Notes |
|---|---|---|---|---|
| **Code-signed exe** (no SmartScreen warning) | 🔴 unsigned | MacWhisper (Developer ID), Buzz (since 2023, Sectigo) | M | Costs ~$200/year for a cert + signing pipeline. Without it, first-launch always trips SmartScreen. |
| **Notarised macOS build** | 🔴 N/A (Windows-only) | MacWhisper, Buzz | XL | Would require porting to a cross-platform toolchain. |
| **Auto-update from inside the app** | 🔴 absent | Buzz (Squirrel), MacWhisper (Sparkle), Vibe | M | `tufup` is the standard PyInstaller-compatible solution. |
| **Per-machine install + per-user override** | 🟡 Inno admin/user choice exists | MacWhisper, Buzz | — | Acceptable; Method B and C do this. |
| **Linux / Flatpak / AppImage** | 🔴 Windows-only | Buzz (.deb, AppImage), Vibe (.deb, AppImage) | L | We chose Windows-only deliberately; revisit if there's demand. |
| **Reproducible builds** | 🔴 not enforced | Tor Project, Reproducible Builds Project | M | A Method-A user who hash-compares the binary to ours would not get a match because of build-time inputs. |
| **Crash reporting** | 🟡 Sentry available but commented out | Buzz uses sentry-sdk | XS | Just uncomment + flip a config; need to add a UI consent toggle. |
| **Opt-in usage telemetry** | 🔴 absent | Vibe (anonymous metrics, off by default), MacWhisper | S | One POST per launch with `{os, version, anonymised_id}`. |
| **GitHub Actions CI** | 🔴 no CI workflows in `.github/` | Buzz (matrix Win/Mac/Linux), Vibe | M | Our 164 unit tests + smoke suite never run against PR diffs from contributors. |
| **Release-notes RSS / API integration** | 🔴 manual `gh release create` | Modern desktop tooling | S | A `latest.json` we can publish so future auto-update can pick it up. |

---

## G. Project / community health

| Feature | Us | Peers | Effort | Notes |
|---|---|---|---|---|
| **Contributor docs** (`CONTRIBUTING.md`) | 🔴 absent | Buzz (full), Vibe (full) | XS | New contributors don't know which tests to run or how to build. |
| **`CODE_OF_CONDUCT.md`** | 🔴 absent | Buzz, Vibe (CC) | XS | Single-page boilerplate; signals a healthy project. |
| **Issue templates** | 🔴 absent (raw "open an issue") | Buzz, Vibe | XS | Bug / feature / question templates reduce triage burden. |
| **PR template** | 🔴 absent | Buzz, Vibe | XS | Reminder for "did you run tests, did you update docs". |
| **Discussions enabled** | 🟡 (status unknown — not used) | Buzz (active), Vibe (active) | XS | Better than Issues for "how do I…" questions. |
| **A test suite that runs in CI** | 🟡 164 tests pass locally but no CI gate | Buzz (GH Actions), Vibe (CI matrix) | M | Local-only tests can drift unnoticed between releases. |
| **Coverage report published** | 🔴 absent (we generate `.coverage` but never publish) | Buzz | XS | Codecov / Coveralls badge in the README. |
| **Versioned API / SDK docs** | 🔴 absent (no public Python API beyond running the app) | MacWhisper (HTTP API in Pro), Buzz (CLI) | M | Anyone wanting to embed our transcription as a library has to copy from `core/`. |
| **Sample data / demo media** in the repo | 🔴 absent (smoke tests need a private E: drive video) | Buzz (small sample), Vibe | XS | A 10 s public-domain clip checked into `tests/fixtures/` would let outside contributors run the smoke suite. |
| **Localised documentation** | 🟡 INSTALL.md has Persian section; rest is English | Buzz (English, Vibe (15+ langs in app) | M | If the UI is going to be internationalised (E above), docs follow. |
| **Versioning policy** (SemVer? CalVer?) | 🟡 we used 0.3 → 0.6 → 0.7 without a stated policy | most | XS | A line in CHANGELOG.md saying which scheme we use. |
| **Stability promise per public API** | 🔴 no contract; users of `core/integrations/` are on their own | rare in this space — fine | — | Worth a note that internal modules may break. |

---

## H. Performance / packaging

| Feature | Us | Peers | Effort | Notes |
|---|---|---|---|---|
| **Onefile size** | 🟢 190.8 MB | Buzz Windows: ~ 220 MB, Vibe: ~ 60 MB (Tauri lighter) | — | Onefile is a reasonable size. |
| **Cold start** | 🟢 ~ 6 s onefile, ~ 3 s onedir/embed | Buzz: ~ 4 s; MacWhisper: < 1 s native | — | Acceptable. |
| **Memory footprint** | 🟡 ~ 2 GB once model is loaded | Buzz (model-dependent same), MacWhisper (Apple Neural Engine — much less) | — | Inherent to faster-whisper large-v3. Smaller model = lower memory. |
| **GPU acceleration tested on each release** | 🔴 only CPU smoke runs in the test suite | Buzz (GPU smoke per release in CI) | S | Without GPU testing, a ctranslate2 / CUDA upgrade can silently break GPU users. |
| **Streaming model download with resume + checksum** | 🟢 already implemented in `core/model_manager.py` | most cloud-down apps lack this | — | Done; better than peers actually. |
| **Quantised model support** (int4, int8, q5_0 from whisper.cpp) | 🟡 only int8 via ctranslate2 | Buzz / Vibe (whisper.cpp ggml q5_0, q4_K_M) | M | Halves model size on disk and 2-3× speed on weak CPUs. |

---

## I. SMTV / yt-dlp / integration

| Feature | Us | Peers | Effort | Notes |
|---|---|---|---|---|
| **yt-dlp passthrough** | 🟢 yes, with auto-transcribe wiring | Buzz (YT URL paste), MacWhisper (YT URL paste) | — | Done. |
| **Supreme Master TV native scraper** | 🟢 yes (Session 11) | nobody else has this | — | **Unique.** |
| **Other niche video site scrapers** (Aparat, ArvanCloud VOD, our user's likely Persian sources) | 🔴 absent | none in this category — but bespoke scrapers are routine | per-site M | Pattern is established by `core/integrations/smtv.py`; copy-paste for new sites. |
| **Subtitle download from YouTube** | 🟢 supports yt-dlp subtitle phase | Buzz/MacWhisper rely on YouTube directly | — | Done. |
| **Live URL (RTMP, HLS) ingestion** | 🔴 absent | Buzz no, Vibe no, WhisperLive yes | L | Would require server-mode and is a different product. |

---

## J. The honest "where do we stand" verdict

We're a **solid local file transcriber** with an **unusual standout** (SMTV native scraping) and a **modern packaging story** (three install methods, audit-clean code, 164 tests). We are also **one of the only Windows-first Whisper apps that bundles the model download + ffmpeg + yt-dlp + a real UI in a single install**, which Buzz and Vibe pieces together with separate steps.

The five things keeping us behind the leaders, in priority order:

1. **Speaker diarization.** Single biggest user-visible gap. Without it, our transcripts of meetings / interviews / podcasts are noticeably less useful than even the free tier of Otter or any MacWhisper output. Effort: L. Impact: 10/10.
2. **In-app transcript viewer with click-to-jump playback.** Even if we never build a full editor, just showing the SRT inside the app — with a play button — closes a huge confidence gap. Effort: M. Impact: 8/10.
3. **DOCX + Markdown export.** Cheap to ship, journalists love it. Effort: S. Impact: 6/10.
4. **System-wide dictation hotkey.** Defines the entire Superwhisper / Wispr Flow category that's growing fastest in 2025/2026. Effort: XL. Impact: 9/10.
5. **CI on GitHub Actions** with our own tests gated on PRs. Without this, every release is "trust me, I ran the smoke locally" — fine for a one-person project, fragile for anyone else who tries to ship a hot-fix. Effort: M. Impact: 7/10 to maintainers. (Code-signing is deferred — current scope decision.)

Everything else in this document is real and reasonable to address over time, but the five above are the ones that change how users describe the product.

---

## Sources

- [MacWhisper feature reviews 2026](https://daveswift.com/macwhisper/), [MacWhisper Pro features](https://www.getvoibe.com/resources/macwhisper-pricing/), [MacWhisper speaker recognition docs](https://macwhisper.helpscoutdocs.com/article/32-automatic-speaker-recognition-in-macwhisper)
- [Buzz Captions GitHub](https://github.com/chidiwilliams/buzz), [Buzz 2026 review](https://www.aitoolsdigest.com/blog/buzz-transcription-app-review-2026), [Buzz docs](https://chidiwilliams.github.io/buzz/docs)
- [Vibe (thewh1teagle)](https://github.com/openai/whisper/discussions/2293), [Tauri+whisper.cpp landscape 2026](https://dev.to/ottoaria/tauri-in-2026-build-cross-platform-desktop-apps-with-web-technologies-better-than-electron-11mo)
- [Superwhisper, Wispr Flow, MacWhisper 2026 comparison](https://spokenly.app/blog/wispr-flow-vs-superwhisper-vs-macwhisper)
- [WhisperX, stable-ts, WhisperKit, Whisper-Streaming, WhisperLive](../docs/COMPETITIVE_ANALYSIS_2026.md#a-open-source-landscape-we-have-not-yet-evaluated)
- [Descript transcript-driven editor product page](https://www.descript.com/)
- Our own [ROADMAP.md](ROADMAP.md) — Phases 4–7 already plan a chunk of this.
