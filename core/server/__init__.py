"""Optional local-network / web HTTP job server for the Whisper Project.

Public surface:

  * :func:`run_server` — bind a :class:`~core.server.httpd.JobHTTPServer`,
    load the Whisper model once (so it stays HOT), start the single-worker
    :class:`~core.server.jobs.JobManager`, and serve forever.
  * :func:`reachable_urls` — the loopback / LAN URLs to print on startup.

Tk-free; imports nothing from ``app/``. Stdlib only (plus the bundled
yt-dlp.exe for URL downloads, the same binary the desktop app uses).
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
from typing import Any

from core.server.httpd import JobHTTPServer
from core.server.jobs import JobManager

logger = logging.getLogger(__name__)

__all__ = ["run_server", "reachable_urls", "JobHTTPServer", "JobManager"]


def _real_transcribe(
    task: Any,
    progress_cb: Any = None,
    log_cb: Any = None,
    language_cb: Any = None,
) -> None:
    """Thin adapter onto ``core.transcriber.transcribe`` (lazy import).

    Imported lazily so ``core.server`` stays importable (and unit-testable)
    without dragging in faster-whisper.
    """
    from core import transcriber as _trans
    _trans.transcribe(task, progress_cb, log_cb, language_cb)


def _download_url(url: str, dest_dir: str) -> str:
    """Download an http(s) ``url`` into ``dest_dir`` via bundled yt-dlp.

    Returns the saved media path. Uses the same end-of-options ``--``
    injection guard the desktop download service uses so a URL that starts
    with ``-`` can never be parsed as a yt-dlp flag (e.g. ``--exec``).
    """
    from core._proc import new_session_kwargs
    from core.paths import bin_dir, bundled_binary

    yt_dlp = bundled_binary("yt-dlp")
    out_template = os.path.join(dest_dir, "%(title).200s.%(ext)s")
    command = [
        yt_dlp,
        "--ffmpeg-location", bin_dir(),
        "--no-playlist",
        "--newline",
        "-o", out_template,
        # End-of-options separator — URL is never treated as a flag.
        "--",
        url,
    ]
    logger.info("server: downloading %s", url)
    subprocess.run(
        command, check=True, capture_output=True, text=True,
        **new_session_kwargs(),
    )
    # Pick the newest file yt-dlp left in the dir.
    candidates = [
        os.path.join(dest_dir, n) for n in os.listdir(dest_dir)
        if os.path.isfile(os.path.join(dest_dir, n))
    ]
    if not candidates:
        raise RuntimeError("download produced no file")
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def _ensure_model_loaded() -> None:
    """Make sure the model is present + loaded before serving.

    Downloads it on first run (same path the GUI uses) then loads it into
    the module-global so the first job doesn't pay the cold-load cost.
    """
    from core import transcriber as _trans
    from core.config import load_config
    from core.model_manager import ensure_model

    cfg = load_config()
    _trans.config.update(cfg)
    try:
        ensure_model(cfg, status_cb=lambda m: logger.info("server: %s", m))
    except Exception as e:  # noqa: BLE001
        logger.warning("server: ensure_model failed (%s); "
                       "the first job may need to download it", e)
    if not _trans.load_existing_model(lambda m: logger.info("server: %s", m)):
        err = _trans.get_model_error() or "unknown error"
        logger.warning("server: model not loaded yet (%s); "
                       "jobs will report the error until it is", err)


def reachable_urls(host: str, port: int) -> list[str]:
    """Human-facing URLs to print on startup.

    For a loopback bind, just the loopback URL. For an all-interfaces bind
    (``0.0.0.0``), the loopback URL plus this machine's best-guess LAN IP so
    the operator can hand the address to people on the network.
    """
    if host not in ("0.0.0.0", "::", ""):
        return [f"http://{host}:{port}/"]
    urls = [f"http://127.0.0.1:{port}/"]
    lan_ip = _primary_lan_ip()
    if lan_ip:
        urls.append(f"http://{lan_ip}:{port}/")
    return urls


def _primary_lan_ip() -> str:
    """Best-effort primary LAN IPv4 (no packets actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connecting a UDP socket just picks the outbound interface; no
        # traffic leaves the machine.
        s.connect(("8.8.8.8", 80))
        return str(s.getsockname()[0])
    except OSError:
        return ""
    finally:
        s.close()


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str = "",
    *,
    max_upload_mb: int = 512,
    load_model: bool = True,
) -> int:
    """Run the HTTP job server forever. Returns a process exit code.

    Binds ``host:port``, loads the model once (unless ``load_model`` is
    False), starts the single-worker JobManager, prints the reachable
    URL(s), and serves until interrupted.
    """
    if load_model:
        _ensure_model_loaded()

    manager = JobManager(_real_transcribe, download_fn=_download_url)
    manager.start()
    try:
        server = JobHTTPServer(
            (host, port), manager, token=token, max_upload_mb=max_upload_mb,
        )
    except OSError as e:
        logger.error("server: could not bind %s:%s — %s", host, port, e)
        manager.stop()
        return 1

    is_lan = host in ("0.0.0.0", "::", "")
    print("Whisper Project server listening on:")
    for url in reachable_urls(host, port):
        print(f"  {url}")
    if is_lan:
        print("LAN mode: bound to all interfaces. Windows Defender may prompt "
              "to allow access — this is expected for the LAN case.")
    else:
        print("Loopback only (this machine). Use --lan to share on the network.")
    if token:
        print("Auth token required (X-Auth-Token header or ?token=).")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.shutdown()
        server.server_close()
        manager.stop()
    return 0
