# Supreme Master TV Integration — Research Notes

> **Status:** Research note. The implementation brief that consumes
> this file is [`smtv-brief.md`](smtv-brief.md). Both files were
> authored together on `release/single-file-exe` to lock scope before
> any production code lands.

## Why this exists

The user expects to "use a lot" of content from
[Supreme Master TV](https://suprememastertv.com/en1/). A teammate
asked for three sub-features:

1. Series download (multi-part episodes pulled together)
2. Audio-only output (mp3)
3. Subtitle / transcript handling (or auto-transcribe as a fallback)

The reference URL the user provided —
`https://suprememastertv.com/en1/v/314924375480.html` — is Part 7 of
a 7-part lecture series. Whatever we build has to handle "give me all
seven parts" as the canonical path.

## Findings

### R1 — Is SMTV in yt-dlp?

No. yt-dlp **2026.03.17** has no `suprememastertv` / `smtv`
extractor:

```
$ ./bin/yt-dlp.exe --list-extractors | findstr /i supreme
(empty)
```

Direct attempts fail both with the dedicated and with the generic
extractors:

```
$ ./bin/yt-dlp.exe -j https://suprememastertv.com/en1/v/314924375480.html
ERROR: Unsupported URL: https://suprememastertv.com/en1/v/314924375480.html

$ ./bin/yt-dlp.exe --force-generic-extractor -v https://suprememastertv.com/en1/v/314924375480.html
[generic] 314924375480: Extracting information
WARNING: [generic] Forcing generic information extractor
[debug] Looking for embeds
ERROR: Unsupported URL: ...
```

The generic extractor's embed-detector finds no recognisable embed
because SMTV exposes the player data through a plain JavaScript
variable assignment, not via a tracked CDN signature or recognisable
JSON-LD.

### R2 — URL structure

| Page             | URL pattern                                                                                                       |
|------------------|-------------------------------------------------------------------------------------------------------------------|
| Home             | `https://suprememastertv.com/{lang}1/`                                                                            |
| Episode          | `https://suprememastertv.com/{lang}1/v/{12-digit-id}.html`                                                        |
| Search (UI)      | `https://suprememastertv.com/{lang}1/search/?q=<term>&type=<TYPE>&category=<CAT>&subtitle=<lang>&audio=<lang>...` |
| Search (results) | `POST https://suprememastertv.com/{lang}1/search/loadmore?<same-querystring>` with `Content-Length: 0` header     |
| Download CDN     | `https://cf-vdo.suprememastertv.com/vod/video/download-mp4.php?file={path}`                                       |

`{lang}` is one of 29 two-letter codes: `en`, `ch` (trad. Chinese),
`gb` (simp. Chinese), `de`, `es`, `fr`, `hu`, `jp`, `kr`, `mn`, `vn`,
`bg`, `ms`, `fa` (Persian), `pt`, `ro`, `id`, `th`, `ar`, `cs`, `pa`,
`pl`, `it`, `tl`, `uk`, `hi`, `pl`, `ru`, `te`. Each language has its
own URL prefix; episode IDs are global across languages.

Content categories observed in the search filters:

| Code   | Title                                                                                |
|--------|--------------------------------------------------------------------------------------|
| `BMD`  | Between Master and Disciples                                                         |
| `VEG`  | Veganism: The Noble Way of Living                                                    |
| `AW`   | Animal World: Our Co-inhabitants                                                     |
| `NWN`  | Noteworthy News                                                                      |
| `AJAR` | A Journey through Aesthetic Realms                                                   |
| `AP`   | Ancient Predictions about Our Planet                                                 |
| `WOW`  | Words of Wisdom                                                                      |
| `GOL`  | A Gift of Love (cooking show)                                                        |
| `SHOW` | Show / variety                                                                       |
| `ADS`  | Shorts (PSA-style)                                                                   |
| … and 20+ more                                                                       |                                                                                       |

### R3 — Where the files live

The episode page contains a JavaScript block that assigns
`videoPlayerData` directly to a global. Sample from
`/en1/v/314324511501.html`:

```js
videoPlayerData["sourceDefault"] = "video";
videoPlayerData["videoPoster"]  = "../../vimages/202605/3143-BMD1.jpg";
videoPlayerData["youTubeUrl"]   = "Cl_Ne-MeU5Y";
videoPlayerData["videoLength"]  = "37:31";
videoPlayerData["vid"]          = "314324511501";
videoPlayerData["start"]        = "0";
videoPlayerData["videoFile"]    = new Array();
videoPlayerData["videoFile"].push(new Array('1080p','2026/0512/3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7-1080p.mp4'));
videoPlayerData["videoFile"].push(new Array('720p', '2026/0512/3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7-2m.mp4'));
videoPlayerData["videoFile"].push(new Array('396p', '2026/0512/3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7-700k.mp4'));
videoPlayerData["videoFile"].push(new Array('audio','2026/0512/3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7.mp3'));
```

Quality tokens observed in the wild:

| Token     | Meaning                                  |
|-----------|------------------------------------------|
| `1080p`   | HD 1080p MP4 (long-form only, ~ 196 MB+) |
| `720p`    | HD 720p MP4 ("2m" suffix; ~ 2 Mbps)      |
| `396p`    | SD 396p MP4 ("700k" suffix; ~ 700 Kbps)  |
| `audio`   | MP3 (BMD/AJAR only; news clips skip it)  |
| (poster)  | JPG photo, not in videoFile array        |

Each `videoFile` entry is `[quality_label, relative_path]`. The
absolute URL is built by prefixing
`https://cf-vdo.suprememastertv.com/vod/video/download-mp4.php?file=`.

Confirmation that the CDN URL works without auth:

```
$ curl -sI "https://cf-vdo.suprememastertv.com/vod/video/download-mp4.php?file=2026/0512/3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7-700k.mp4"
HTTP/1.1 200 OK
Content-Type: octet/stream
Content-Length: 196898566
Content-disposition: attachment; filename=3143-BMD-19951224-Shivas-112-Ways-of-Concentration-I-p1o7-700k.mp4
Server: cloudflare
```

**Not** HLS, **not** DASH, **not** embedded behind a JWPlayer-style
signed URL. Plain HTTPS GET with `Content-Disposition: attachment`.

Series structure is on the episode page itself: every part of the
same series is linked from a `<div class="playlist-contaner">` block
on every episode page. For the reference URL the block contains:

```
<a href="../v/314324511501.html" title="… Part 1 of 7 …">… Part 1 of 7</a>
<a href="../v/314424544835.html" title="… Part 2 of 7 …">… Part 2 of 7</a>
<a href="../v/314524462507.html" title="… Part 3 of 7 …">… Part 3 of 7</a>
…
<a href="../v/314924375480.html" title="… Part 7 of 7 …">… Part 7 of 7</a>
```

Title format `… Part {N} of {M} …` is a strong, regex-able signal.

### R4 — Subtitles and transcripts

There is **no separate subtitle file** per episode. The lecture
videos carry **burned-in subtitles** (the player has an "Enlarge
Subtitles" button — `bigsubtitle.html`).

The page does carry a **full text transcript** as HTML, inside
`<div class="article-text" id="article-text">`. A "Download Docx"
button generates a .docx **client-side** with `html-docx.js` —
there is no server endpoint for the docx.

Captured from `/en1/v/314324511501.html`:

```html
<div class="article-body">
  <div class="details">…</div>
  <div class="text" id="article-text-container">
    …
    <div class="article-text" id="article-text">
      <p>You guys are experts at eating. (Hallo, Master.) …</p>
      …
    </div>
  </div>
</div>
```

So our path to a transcript is: scrape that div as text and save
alongside the video. This is the "subtitle or transcript" answer for
sub-feature 3.

For the fallback case (page lacks `article-text`, e.g. some short
clips), we use the existing Phase 3a
*auto-transcribe-after-download* wiring on the downloaded MP3 / MP4.

### R5 — Rate limiting, captcha, session

- `robots.txt` contains only `Sitemap: …`, no `User-agent` or
  `Disallow` lines.
- No captcha on any page hit during research (episode, search,
  loadmore, CDN GET).
- No cookies / session needed; a vanilla `Mozilla/5.0` UA is enough.
- Cloudflare fronts the CDN, but the requests passed JS-challenge-
  free with a standard UA. We should still honour Cloudflare's
  expected rate (one request per second per file is safe; we already
  use yt-dlp's defaults elsewhere) and **not** retry aggressively on
  429.
- Search `loadmore` requires a POST with an explicit `Content-Length:
  0` header. Forgetting the header returns 411.

### R6 — License / ToS

| Source                | Statement                                                                                                   |
|-----------------------|-------------------------------------------------------------------------------------------------------------|
| Footer of every page  | `Copyright © The Supreme Master Ching Hai International Association. All Rights Reserved.`                  |
| Dedicated ToS page    | Not found. The site has Home / About Us / Contact Us / Related Links / App; no Terms / Privacy / Disclaimer |
| robots.txt            | Empty of restrictions                                                                                       |
| Episode page UI       | Provides explicit `Download` buttons for HD 1080p / HD 720p / SD 396p / Audio mp3 / Photo / Docx            |
| CDN response          | `Content-Disposition: attachment` — the server is configured to *serve* downloads, not stream-only          |

There is no ToS that explicitly prohibits downloading; the site's
own UI directs users to download. We proceed without a separate user
confirmation, treating this as the same posture as the YouTube
integration (personal-use copyrighted material — caller's
responsibility).

### R7 — Prior art

- GitHub search for `suprememastertv downloader`, `smtv-downloader`,
  `supreme master TV scraper` — no hits.
- yt-dlp issues tracker search — no extractor request, no open
  request to add SMTV.
- Stack Overflow / generic Google — no community tooling.

No prior art to copy or learn from. Implementation will be original
and based directly on the page-scrape findings above.

## Implementation options

### Option A — yt-dlp plugin

Add `core/integrations/yt_dlp_plugins/extractor/smtv.py` exposing a
`SmtvIE` extractor class. yt-dlp's plugin loader picks it up at
runtime.

* Pros: end users could later use `yt-dlp <smtv-url>` directly; we
  inherit yt-dlp's progress / resume / retry machinery for free.
* Cons: plugin discovery inside a PyInstaller onefile bundle is
  finicky (the extractor must live at a discoverable path inside
  `sys._MEIPASS`); yt-dlp pins extractor APIs and we'd have to track
  them. Also: the actual extractor class is < 60 lines because the
  scrape is trivial — we'd carry the abstraction tax without much
  return.

### Option B — Pure-Python module + own HTTP download

`core/integrations/smtv.py` with `urllib.request` and `re`. The
`download_service` detects SMTV URLs and dispatches to a new internal
helper that:

1. Hits the episode page
2. Parses `videoPlayerData["videoFile"]` and the playlist sibling
   list and the article transcript
3. Downloads the chosen quality straight to the user's chosen folder,
   streaming with a chunked write and posting `progress` events into
   the existing `DownloadEvents` queue
4. Optionally writes the transcript next to the video

* Pros: no yt-dlp plugin gymnastics; zero new runtime deps;
  surface-area is small and entirely under our control; downloads
  fit naturally into the existing `DownloadService` queue
  semantics; works identically in onefile, onedir, and source modes.
* Cons: we re-implement progress/resume that yt-dlp would have given
  us — but the SMTV CDN supports `Range` headers so resume is one
  extra `if`, and progress is already a percentage off
  `Content-Length`.

### Option C — Hybrid: scrape with our code, download with yt-dlp

Module resolves the page → returns CDN URLs → invokes
`yt-dlp <direct-url>` with `--no-playlist` to download.

* Pros: yt-dlp handles HTTP fine, including resume.
* Cons: extra subprocess hop for what is a direct HTTP GET; yt-dlp
  treats a `download-mp4.php?file=…` URL as a "generic" download
  anyway, so we lose nothing by skipping it. Adds latency on every
  download (~ 1 s yt-dlp warm-up).

### Option D — Bash out to existing `bin/yt-dlp.exe` for *every* SMTV URL via a custom extractor file written to `_MEIPASS/yt_dlp_plugins`

Like Option A but the plugin lives at build time only. Same yt-dlp
internals concern; bigger build-time complexity. Rejected.

### Recommended: Option B

The scrape is so direct (regex out a JS array, regex out sibling
hrefs) that bringing in yt-dlp adds more cost than benefit. We get
predictable behaviour, zero new bundle weight, and the same event
shape as the existing yt-dlp-driven flow — so `DownloadService.poll`,
the queue tab, history.db, and auto-transcribe-after-download all
keep working unchanged.

## Known traps

| Trap                                                             | Mitigation                                                                                                                                                                |
|------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `videoPlayerData` may be inlined in the page or fetched lazily   | All episode pages observed so far inline it. Detect "not found" and fall back to an explicit error (don't silently produce a broken download).                            |
| Quality tokens vary (`1080p`/`720p`/`396p`/`audio`; news skips mp3) | Iterate the array; never assume a fixed quality exists.                                                                                                                   |
| Sibling list also includes "Related" videos (not the series)     | Filter siblings by title prefix: same text up to "Part N of M". Verified working on the reference URL.                                                                    |
| Page is multilingual; `/fa1/v/<id>.html` exists too              | Accept any `^/[a-z]{2,3}1/v/\d+\.html$` path. Always download from the same language we landed on (transcript would otherwise mismatch the audio).                        |
| CDN occasionally throttles bursts                                | Single connection per file. No parallel within an episode. Existing `parallel_workers=2` cap still applies across episodes in a series.                                   |
| `html-docx.js`-built docx is client-side only                    | We do *not* attempt to reproduce that docx. We save the visible transcript text instead. Users wanting docx can use the website's own button.                             |
| Burned-in subtitles in the video                                 | The video already has visible subtitles. Don't tell the user "no subtitles" — call it "transcript saved" instead.                                                          |
| Site has subtitles in 29 languages on the video itself           | The language of the burned-in subtitles depends on which `/{lang}1/` page the user came from. We currently expose this implicitly through the URL — no UI surfacing needed for v1. |
| `Copyright © All Rights Reserved` on every page                  | We surface the warning text in the README / INSTALL section, matching the precedent set by YouTube downloads in the existing tab.                                          |

## Sources

- Reference series page: `https://suprememastertv.com/en1/v/314924375480.html`
- Sample episode 1 of 7: `https://suprememastertv.com/en1/v/314324511501.html`
- Sample news clip: `https://suprememastertv.com/en1/v/314951825753.html`
- Search root: `https://suprememastertv.com/en1/search/`
- Search loadmore endpoint: `POST https://suprememastertv.com/en1/search/loadmore?<params>` (Content-Length: 0)
- CDN endpoint: `https://cf-vdo.suprememastertv.com/vod/video/download-mp4.php?file=<path>`
- robots.txt: `https://suprememastertv.com/robots.txt`
- Site footer copyright statement (homepage)
