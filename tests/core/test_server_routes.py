"""Pure-helper tests for the LAN server's route / query / multipart parsing.

No socket, no model, no Tk. These lock the contract the request handler
dispatches on — a dropped route or a mis-parsed upload is exactly how a
hard-to-spot server bug ships.
"""
from __future__ import annotations

from core.server.httpd import (
    extract_upload,
    normalize_formats,
    parse_multipart_filename,
    parse_route,
    token_ok,
)
from core.server.jobs import _safe_filename, is_safe_url


# --- parse_route -------------------------------------------------------------

def test_route_root():
    assert parse_route("GET", "/").name == "root"
    assert parse_route("GET", "").name == "root"


def test_route_health_and_formats():
    assert parse_route("GET", "/api/health").name == "health"
    assert parse_route("GET", "/api/formats").name == "formats"


def test_route_jobs_collection_vs_item():
    assert parse_route("POST", "/api/jobs").name == "jobs"
    r = parse_route("GET", "/api/jobs/deadbeef")
    assert r.name == "job"
    assert r.job_id == "deadbeef"


def test_route_result_and_cancel_extract_id_and_query():
    r = parse_route("GET", "/api/jobs/xyz/result?fmt=srt")
    assert (r.name, r.job_id, r.query["fmt"]) == ("result", "xyz", "srt")
    c = parse_route("POST", "/api/jobs/xyz/cancel")
    assert (c.name, c.job_id) == ("cancel", "xyz")


def test_route_trailing_slash_is_tolerated():
    assert parse_route("GET", "/api/health/").name == "health"
    assert parse_route("GET", "/api/jobs/abc/").name == "job"


def test_route_unknown_is_404_signal():
    assert parse_route("GET", "/api/nope").name == "unknown"
    assert parse_route("GET", "/api/jobs/a/b/c/d").name == "unknown"


def test_route_query_flattens_to_first_value():
    r = parse_route("GET", "/api/jobs/a/result?fmt=srt&fmt=vtt&token=t")
    assert r.query["fmt"] == "srt"
    assert r.query["token"] == "t"


# --- token_ok ----------------------------------------------------------------

def test_token_ok_open_when_no_secret():
    assert token_ok("", None, None) is True
    assert token_ok("", "anything", None) is True


def test_token_ok_accepts_header_or_query():
    assert token_ok("s3cret", "s3cret", None) is True
    assert token_ok("s3cret", None, "s3cret") is True


def test_token_ok_rejects_wrong_or_missing():
    assert token_ok("s3cret", None, None) is False
    assert token_ok("s3cret", "nope", "nope") is False


# --- normalize_formats -------------------------------------------------------

def test_normalize_formats_csv_and_list_drop_unknown():
    assert normalize_formats("srt,bogus,docx") == ["srt", "docx"]
    assert normalize_formats(["vtt", "json", "exe"]) == ["vtt", "json"]


def test_normalize_formats_dedupes_preserving_order():
    assert normalize_formats("srt,srt,txt,srt") == ["srt", "txt"]


def test_normalize_formats_falls_back_to_srt():
    assert normalize_formats(None) == ["srt"]
    assert normalize_formats("garbage,more") == ["srt"]
    assert normalize_formats([]) == ["srt"]


# --- multipart ---------------------------------------------------------------

def test_parse_multipart_boundary():
    assert parse_multipart_filename("multipart/form-data; boundary=ABC") == "ABC"
    assert parse_multipart_filename('multipart/form-data; boundary="Q\"') == "Q"
    assert parse_multipart_filename("application/json") == ""
    assert parse_multipart_filename(None) == ""


def test_extract_upload_pulls_file_and_fields():
    boundary = "BB"
    body = (
        b"--BB\r\n"
        b'Content-Disposition: form-data; name="formats"\r\n\r\n'
        b"srt,txt\r\n"
        b"--BB\r\n"
        b'Content-Disposition: form-data; name="language"\r\n\r\n'
        b"en\r\n"
        b"--BB\r\n"
        b'Content-Disposition: form-data; name="file"; filename="clip.mp4"\r\n'
        b"Content-Type: video/mp4\r\n\r\n"
        b"RAWBYTES\r\n"
        b"--BB--\r\n"
    )
    filename, file_bytes, fields = extract_upload(body, boundary)
    assert filename == "clip.mp4"
    assert file_bytes == b"RAWBYTES"
    assert fields == {"formats": "srt,txt", "language": "en"}


def test_extract_upload_no_boundary_is_empty():
    assert extract_upload(b"whatever", "") == ("", b"", {})


# --- jobs.is_safe_url / _safe_filename --------------------------------------

def test_is_safe_url_accepts_http_https_only():
    assert is_safe_url("http://example.com/v") is True
    assert is_safe_url("https://youtu.be/abc") is True
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("ftp://host/x") is False
    assert is_safe_url("/local/path") is False
    assert is_safe_url("") is False
    assert is_safe_url("https://") is False  # no host


def test_safe_filename_strips_paths_and_traversal():
    assert _safe_filename("clip.mp4") == "clip.mp4"
    assert _safe_filename("../../etc/passwd") == "passwd"
    assert _safe_filename("a/b/c.mkv") == "c.mkv"
    # All-suspect input falls back to a generated name.
    got = _safe_filename("../")
    assert got.startswith("upload-") and got.endswith(".bin")
