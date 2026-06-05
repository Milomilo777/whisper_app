# Local-network / web server mode

An optional HTTP job server so other people on your network can transcribe
through a web browser instead of each installing the desktop app. It reuses
the same engine the desktop app uses (`core.transcriber`) and adds no new
third-party dependency — it is built on the Python standard library
(`http.server`).

> Trusted-network use only. There is no user accounts system; anyone who can
> reach the address (and present the optional token) can submit jobs and
> download results. Run it on a network you trust.

## Start it

```
python gui.py serve
```

That binds **loopback only** (`127.0.0.1:8765`) — reachable just from the
machine it runs on, and it never triggers a Windows firewall prompt. Open
the printed URL in a browser on the same machine.

To share it with other devices on your LAN, opt in explicitly:

```
python gui.py serve --lan
```

`--lan` binds all network interfaces (`0.0.0.0`). **This is the only mode
that triggers the Windows Defender firewall prompt** — that prompt is
expected, and you must allow access for other devices to connect. On
startup the server prints the LAN URL (e.g. `http://192.168.1.42:8765/`) to
hand to people on the network.

Options:

```
--port 9000              # listen port (default: config server_port, 8765)
--host 0.0.0.0           # explicit bind address (same effect as --lan)
--token SECRET           # require a shared secret (see Security below)
--max-upload-mb 200      # reject uploads larger than this (default 512)
```

The server loads the Whisper model once at startup and keeps it hot, then
processes jobs **one at a time** (a single background worker). Sequential
processing is intentional: the ~3 GB model lives in a process global and
running transcriptions concurrently against it is unsafe.

## What the browser page does

The page (served at `/`) lets a user:

1. pick a local file **or** paste a link (anything yt-dlp supports),
2. choose output formats (the checkboxes are populated from what the
   server reports),
3. optionally set a language code,
4. start the job and watch progress,
5. download each produced file when it finishes.

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET  | `/` | the browser page |
| GET  | `/api/health` | `{status, version, formats}` |
| GET  | `/api/formats` | `{formats}` |
| POST | `/api/jobs` | create a job — multipart upload OR JSON `{url, formats, language}` → `{job_id}` |
| GET  | `/api/jobs/<id>` | `{status, progress, error, outputs:[{fmt, name}]}` |
| GET  | `/api/jobs/<id>/result?fmt=srt` | download one written output |
| POST | `/api/jobs/<id>/cancel` | flag the job for cancellation |

`status` is one of `queued`, `downloading`, `running`, `finished`,
`error`, `cancelled`.

## Security caveats

- **Trusted network only.** No authentication beyond the optional token,
  no encryption (plain HTTP). Do not expose it to the open internet.
- **Optional token.** Pass `--token SECRET`; clients must then send it via
  the `X-Auth-Token` header or a `?token=SECRET` query parameter. Without a
  token every request is accepted.
- **Audio is uploaded to the host.** Uploaded media is written to a
  per-job temp directory under the host's cache folder
  (`%LOCALAPPDATA%\WhisperProject\Cache\server_jobs\<id>\`) and the outputs
  are written beside it. Per-job directories are cleaned up as jobs are
  evicted.
- **Upload size cap.** A single upload is capped (`--max-upload-mb`,
  default 512 MB) and rejected with HTTP 413 before being buffered.
- **URL safety.** Only `http`/`https` URLs are accepted (no `file://`).
  yt-dlp performs the actual download with an end-of-options `--` guard so
  a URL can never be parsed as a yt-dlp flag.
- **Bounded queue.** Total and queued job counts are capped; once full the
  server replies HTTP 503.

## Configuration

Two keys in `config.json` (see [CONFIG.md](CONFIG.md)) set the defaults the
`serve` subcommand uses when its flags are omitted:

```
server_port            8765
server_max_upload_mb   512
```
