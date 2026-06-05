"""Stdlib-only HTTP job server for the Whisper Project.

A ``ThreadingHTTPServer`` plus a typed ``BaseHTTPRequestHandler`` that
exposes a tiny JSON API and one static page so people on a trusted LAN
transcribe through a browser instead of each installing the desktop app.

Routes
------
  GET  /                          -> the bundled static index.html
  GET  /api/health                -> {status, version, formats}
  GET  /api/formats               -> {formats}
  POST /api/jobs                  -> create a job (multipart upload OR
                                     JSON {"url", "formats", "language"})
                                     -> {job_id}
  GET  /api/jobs/<id>             -> {status, progress, error, outputs}
  GET  /api/jobs/<id>/result?fmt= -> stream the written output as download
  POST /api/jobs/<id>/cancel      -> flag the job for cancellation

Design constraints honoured here:
  * No third-party deps — only the standard library.
  * Tk-free; imports nothing from ``app/``.
  * Route / query / multipart parsing live in small PURE helpers below so
    they can be unit-tested without binding a socket (mirroring how
    ``app/services`` exposes pure ``build_*`` seams).
  * Optional shared-secret auth via ``X-Auth-Token`` header or ``?token=``.
  * A hard max-upload-size cap enforced before any bytes are buffered.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, NamedTuple

from core import __version__
from core.server.jobs import JobManager, QueueFull
from core.writers import supported_formats

logger = logging.getLogger(__name__)

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Hard ceiling regardless of config, so a typo in config can't open the
# door to an unbounded upload. The configured cap is min()'d against this.
_ABSOLUTE_MAX_UPLOAD_MB = 4096


# --- pure parsing helpers (unit-testable, no socket needed) ------------------

class Route(NamedTuple):
    """A parsed request line split into the pieces the handler dispatches on."""

    method: str
    # Logical route name, e.g. "root", "health", "formats", "jobs",
    # "job", "result", "cancel", or "unknown".
    name: str
    # Path-extracted job id for /api/jobs/<id>[/...] routes, else "".
    job_id: str
    query: dict[str, str]


def parse_route(method: str, raw_path: str) -> Route:
    """Map ``(method, path)`` onto a logical route without touching a socket.

    Unknown paths resolve to ``name="unknown"`` so the handler returns 404.
    Query values are flattened to their first occurrence (single-valued API).
    """
    split = urllib.parse.urlsplit(raw_path)
    path = split.path.rstrip("/") or "/"
    query = {k: (v[0] if v else "")
             for k, v in urllib.parse.parse_qs(split.query).items()}
    parts = [p for p in path.split("/") if p]

    m = method.upper()
    if path == "/" or path == "":
        return Route(m, "root", "", query)
    if parts == ["api", "health"]:
        return Route(m, "health", "", query)
    if parts == ["api", "formats"]:
        return Route(m, "formats", "", query)
    if parts == ["api", "jobs"]:
        return Route(m, "jobs", "", query)
    if len(parts) == 3 and parts[0] == "api" and parts[1] == "jobs":
        return Route(m, "job", parts[2], query)
    if (len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs"
            and parts[3] == "result"):
        return Route(m, "result", parts[2], query)
    if (len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs"
            and parts[3] == "cancel"):
        return Route(m, "cancel", parts[2], query)
    return Route(m, "unknown", "", query)


def token_ok(expected: str, header_token: str | None,
             query_token: str | None) -> bool:
    """Auth gate. When no token is configured, every request passes.

    Otherwise the request must present the matching secret via the
    ``X-Auth-Token`` header OR the ``?token=`` query parameter.
    """
    if not expected:
        return True
    return header_token == expected or query_token == expected


def parse_multipart_filename(content_type: str | None) -> str:
    """Pull the multipart boundary's significance out of a Content-Type.

    Returns the boundary string for a multipart/form-data body, or "" when
    the content type is not multipart. Kept tiny + pure so the handler's
    decision ("is this an upload or a JSON body?") is testable.
    """
    if not content_type:
        return ""
    ctype = content_type.lower()
    if not ctype.startswith("multipart/form-data"):
        return ""
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            return part[len("boundary="):].strip('"')
    return ""


def extract_upload(body: bytes, boundary: str) -> tuple[str, bytes,
                                                        dict[str, str]]:
    """Parse a multipart/form-data body into ``(filename, file_bytes, fields)``.

    A deliberately small parser for exactly the shape this server's own
    page sends: one ``file`` part plus optional plain ``formats`` /
    ``language`` text fields. Returns ``("", b"", fields)`` when no file
    part is present. Pure (no I/O) so it is unit-testable.
    """
    if not boundary:
        return "", b"", {}
    delim = b"--" + boundary.encode("latin-1")
    fields: dict[str, str] = {}
    filename = ""
    file_bytes = b""
    for chunk in body.split(delim):
        if not chunk or chunk in (b"--\r\n", b"--", b"\r\n"):
            continue
        # Strip a single leading CRLF that follows the boundary line.
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        head_end = chunk.find(b"\r\n\r\n")
        if head_end == -1:
            continue
        raw_headers = chunk[:head_end].decode("latin-1", "replace")
        value = chunk[head_end + 4:]
        # Trailing CRLF before the next boundary.
        if value.endswith(b"\r\n"):
            value = value[:-2]
        name = _header_param(raw_headers, "name")
        fname = _header_param(raw_headers, "filename")
        if fname:
            filename = fname
            file_bytes = value
        elif name:
            fields[name] = value.decode("utf-8", "replace")
    return filename, file_bytes, fields


def _header_param(raw_headers: str, key: str) -> str:
    """Find ``key="value"`` inside a Content-Disposition header block."""
    needle = f'{key}="'
    for line in raw_headers.split("\r\n"):
        idx = line.find(needle)
        if idx == -1:
            continue
        rest = line[idx + len(needle):]
        end = rest.find('"')
        if end == -1:
            continue
        return rest[:end]
    return ""


def normalize_formats(raw: Any) -> list[str]:
    """Coerce a formats value (list, CSV string, or None) to known formats.

    Drops unknown names; falls back to ``["srt"]`` when nothing valid is
    left so a job always has at least one output to write.
    """
    available = set(supported_formats())
    items: list[str]
    if isinstance(raw, str):
        items = [p.strip() for p in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        items = [str(p).strip() for p in raw]
    else:
        items = []
    out = [p.lower() for p in items if p and p.lower() in available]
    # Preserve order, de-dupe.
    seen: set[str] = set()
    deduped = [p for p in out if not (p in seen or seen.add(p))]
    return deduped or ["srt"]


# --- the HTTP server ---------------------------------------------------------

class JobHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying the shared JobManager + auth token."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int],
                 manager: JobManager, *, token: str = "",
                 max_upload_mb: int = 512) -> None:
        self.manager = manager
        self.token = token
        self.max_upload_bytes = (
            min(max(1, max_upload_mb), _ABSOLUTE_MAX_UPLOAD_MB) * 1024 * 1024
        )
        super().__init__(server_address, JobRequestHandler)


class JobRequestHandler(BaseHTTPRequestHandler):
    """Typed request handler dispatching the small JSON API + static page."""

    server_version = "WhisperProjectServer/" + __version__
    protocol_version = "HTTP/1.1"

    # narrow the loosely-typed server attr for the type checker
    @property
    def _srv(self) -> JobHTTPServer:
        srv = self.server
        assert isinstance(srv, JobHTTPServer)
        return srv

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.info("%s - %s", self.address_string(), format % args)

    # --- shared helpers ------------------------------------------------------

    def _route(self) -> Route:
        return parse_route(self.command, self.path)

    def _authed(self, route: Route) -> bool:
        return token_ok(
            self._srv.token,
            self.headers.get("X-Auth-Token"),
            route.query.get("token"),
        )

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _send_error_json_close(self, status: int, message: str) -> None:
        """Send an error and close the connection.

        Used when we reject a request WITHOUT consuming its body (the
        oversized-upload path). Under HTTP/1.1 keep-alive an unread body
        desyncs the connection, so the next read would mangle the client's
        bytes — close instead of trying to keep the socket alive.
        """
        body = json.dumps({"error": message}).encode("utf-8")
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    # --- GET -----------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        route = self._route()
        if route.name == "root":
            self._serve_index()
            return
        if not self._authed(route):
            self._send_error_json(HTTPStatus.UNAUTHORIZED, "auth required")
            return
        if route.name == "health":
            self._send_json(HTTPStatus.OK, {
                "status": "ok",
                "version": __version__,
                "formats": supported_formats(),
            })
        elif route.name == "formats":
            self._send_json(HTTPStatus.OK, {"formats": supported_formats()})
        elif route.name == "job":
            job = self._srv.manager.get(route.job_id)
            if job is None:
                self._send_error_json(HTTPStatus.NOT_FOUND, "no such job")
            else:
                self._send_json(HTTPStatus.OK, job.public_dict())
        elif route.name == "result":
            self._serve_result(route)
        else:
            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")

    def _serve_index(self) -> None:
        path = os.path.join(_STATIC_DIR, "index.html")
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self._send_error_json(HTTPStatus.NOT_FOUND, "index missing")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_result(self, route: Route) -> None:
        fmt = route.query.get("fmt", "")
        if not fmt:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "fmt required")
            return
        path = self._srv.manager.output_path(route.job_id, fmt)
        if not path or not os.path.isfile(path):
            self._send_error_json(HTTPStatus.NOT_FOUND, "no such output")
            return
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self._send_error_json(HTTPStatus.NOT_FOUND, "output unreadable")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(path)}"',
        )
        self.end_headers()
        self.wfile.write(body)

    # --- POST ----------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        route = self._route()
        if not self._authed(route):
            self._send_error_json(HTTPStatus.UNAUTHORIZED, "auth required")
            return
        if route.name == "jobs":
            self._create_job()
        elif route.name == "cancel":
            ok = self._srv.manager.cancel(route.job_id)
            if ok:
                self._send_json(HTTPStatus.OK, {"cancelled": route.job_id})
            else:
                self._send_error_json(
                    HTTPStatus.NOT_FOUND, "no such active job")
        else:
            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")

    def _read_body(self) -> bytes | None:
        """Read the request body, enforcing the max-upload cap.

        Returns ``None`` after sending a 413 when the declared length
        exceeds the cap (the worker's 1 MB JSON guard does NOT cover
        uploads, so this is the only size gate on the upload path).
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            length = 0
        if length < 0:
            self._send_error_json_close(HTTPStatus.BAD_REQUEST, "bad length")
            return None
        if length > self._srv.max_upload_bytes:
            # Drain + discard the oversized body in bounded chunks before
            # replying, so the client finishes sending and reliably reads
            # the 413 (an immediate close races the still-uploading client
            # into a connection-reset on Windows). We never buffer it.
            self._drain_body(length)
            self._send_error_json_close(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"upload exceeds {self._srv.max_upload_bytes // (1024 * 1024)} MB cap",
            )
            return None
        return self.rfile.read(length) if length else b""

    def _drain_body(self, length: int) -> None:
        """Read + discard ``length`` bytes from the request body in chunks.

        Used on the reject path so an oversized upload is consumed (never
        buffered whole) and the client can read our response instead of
        hitting a mid-upload connection reset.
        """
        remaining = length
        chunk = 64 * 1024
        try:
            while remaining > 0:
                buf = self.rfile.read(min(chunk, remaining))
                if not buf:
                    break
                remaining -= len(buf)
        except OSError:
            pass

    def _create_job(self) -> None:
        ctype = self.headers.get("Content-Type", "")
        boundary = parse_multipart_filename(ctype)
        body = self._read_body()
        if body is None:
            return  # error already sent (cap exceeded / bad length)
        manager = self._srv.manager
        try:
            if boundary:
                filename, file_bytes, fields = extract_upload(body, boundary)
                if not filename or not file_bytes:
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST, "no file part in upload")
                    return
                formats = normalize_formats(fields.get("formats"))
                language = fields.get("language", "")
                job_id = manager.submit_upload(
                    filename, file_bytes, formats, language)
            else:
                try:
                    data = json.loads(body.decode("utf-8") or "{}")
                except (ValueError, UnicodeDecodeError):
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST, "invalid JSON body")
                    return
                if not isinstance(data, dict):
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST, "JSON object expected")
                    return
                url = str(data.get("url", "")).strip()
                if not url:
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST,
                        "provide a file upload or a JSON url")
                    return
                formats = normalize_formats(data.get("formats"))
                language = str(data.get("language", ""))
                job_id = manager.submit_url(url, formats, language)
        except ValueError as e:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(e))
            return
        except QueueFull as e:
            self._send_error_json(HTTPStatus.SERVICE_UNAVAILABLE, str(e))
            return
        self._send_json(HTTPStatus.ACCEPTED, {"job_id": job_id})
