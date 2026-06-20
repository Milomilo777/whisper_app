"""Optional cloud transcription backend via the NVIDIA Nemotron 3.5 ASR API.

This backend streams audio to NVIDIA's hosted Riva ASR service (NVCF) and
transcribes it with the Nemotron-3.5 streaming model. It is **opt-in** and
breaks the project's "everything stays on this machine" guarantee — the audio
leaves the device. The UI makes that trade-off explicit.

API contract (NVIDIA Riva / NVCF, gRPC streaming)
--------------------------------------------------
* pip package : nvidia-riva-client  (import name: riva.client) — NOT bundled.
  Installed on-demand on first use via core.optional_deps.
* Server URI  : grpc.nvcf.nvidia.com:443  with use_ssl=True
* Auth via NVCF metadata:
    ["function-id", "<nemotron-asr-streaming function id>"]
    ["authorization", "Bearer <NVIDIA_API_KEY>"]
* The model is streaming-only; each audio chunk is sent as a 16 kHz mono PCM
  WAV file via AudioChunkFileIterator and the streaming_response_generator.
* Word timestamps are integers in MILLISECONDS; we divide by 1000.0.
* gRPC errors are grpc.RpcError with .code() (grpc.StatusCode) + .details().

Free-tier note
--------------
NVIDIA offers a limited free call quota on build.nvidia.com for the hosted
Nemotron ASR Streaming endpoint. A free API key can be generated at:
    https://build.nvidia.com  ->  Nemotron ASR Streaming  ->  Get API Key
Approximately 40 BCP-47 locales are supported; the default is en-US. Set
nvidia_asr_language in Advanced > Backend to override (empty = en-US).
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable

from ..config import load_config
from .base import Backend, LanguageInfo
from .cloud_stt import offset_segments, plan_chunks

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- constants

NVIDIA_SERVER = "grpc.nvcf.nvidia.com:443"
NVIDIA_FUNCTION_ID = "bb0837de-8c7b-481f-9ec8-ef5663e9c1fa"
DEFAULT_LANGUAGE = "en-US"
DEFAULT_CHUNK_SECONDS = 300.0

#: WAV 16 kHz mono PCM-s16le is the format Riva ASR streaming expects.
CHUNK_MIME = "audio/wav"
CHUNK_EXT = ".wav"

#: An empty past-EOF slice decodes to just the WAV header (~44 bytes, up to
#: ~80 with ffmpeg's fact/LIST chunks). 1 s of 16 kHz mono s16le is 32 000
#: bytes, so this ceiling never trips on a real (non-empty) chunk but reliably
#: detects an end-of-file empty slice on the unknown-duration path. (44 bytes
#: was too tight — a header with an extra chunk could slip past it.)
_EMPTY_WAV_BYTES = 2048


# ---------------------------------------------------------------- pure seams
# Everything below is network-free and unit-testable without riva installed.


def normalize_language_code(language: str | None) -> str:
    """Map a language hint to a Riva-compatible BCP-47 locale string.

    Rules (intentionally simple — a full mapping is not needed):

    * None or empty string -> default "en-US".
    * A code that already contains "-" is passed through verbatim (e.g.
      "es-US", "fr-FR") — the caller is assumed to know the exact locale.
    * A two-letter code without a region tag (e.g. "en", "fr") is promoted
      to "en-US" (default) or returned as-is so callers that do not know the
      region can at least signal the language; the model may correct silently.

    Nemotron supports ~40 locales. This helper keeps the common case clean
    while still allowing an expert to paste the exact BCP-47 tag in the
    config field and have it pass through unchanged.
    """
    if not language:
        return DEFAULT_LANGUAGE
    lang = language.strip()
    if not lang:
        return DEFAULT_LANGUAGE
    # Already a full BCP-47 locale (contains a hyphen).
    if "-" in lang:
        return lang
    # Bare two-letter code: promote "en" to the full default; other codes
    # are returned as-is rather than guessing a wrong region tag.
    if lang.lower() == "en":
        return DEFAULT_LANGUAGE
    return lang


def results_to_segments(results: Any) -> list[dict[str, Any]]:
    """Convert Riva streaming-response objects to segment dicts.

    Duck-typed so the parser works without riva installed. Each *response*
    in ``results`` is expected to carry a ``.results`` list; each result
    carries ``.is_final`` (bool, absent = True) and ``.alternatives`` (list).
    ``alternatives[0]`` has ``.transcript`` (str) and ``.words`` (list of
    objects with ``.word``, ``.start_time`` (ms int), ``.end_time`` (ms int),
    ``.confidence`` (float)).

    Empty transcripts are silently skipped. Words timestamps are divided by
    1000.0 to convert from milliseconds to seconds.

    Returns a list of ``{start, end, text, words}`` dicts (empty list when
    no final results with text are found).
    """
    segments: list[dict[str, Any]] = []
    try:
        response_list = list(results)
    except Exception:  # noqa: BLE001
        return segments

    for response in response_list:
        inner_results = getattr(response, "results", None)
        if not inner_results:
            continue
        for result in inner_results:
            # is_final defaults to True when absent (old / simple mocks).
            if not getattr(result, "is_final", True):
                continue
            alternatives = getattr(result, "alternatives", None)
            if not alternatives:
                continue
            alt = alternatives[0]
            transcript = (getattr(alt, "transcript", None) or "").strip()
            if not transcript:
                continue

            word_list: list[dict[str, Any]] = []
            raw_words = getattr(alt, "words", None) or []
            seg_start = 0.0
            seg_end = 0.0
            for i, w in enumerate(raw_words):
                start_s = float(getattr(w, "start_time", 0)) / 1000.0
                end_s = float(getattr(w, "end_time", 0)) / 1000.0
                word_text = str(getattr(w, "word", ""))
                confidence = float(getattr(w, "confidence", 1.0))
                word_list.append({
                    "start": start_s,
                    "end": end_s,
                    "word": word_text,
                    "probability": confidence,
                })
                if i == 0:
                    seg_start = start_s
                seg_end = end_s

            segments.append({
                "start": seg_start,
                "end": seg_end,
                "text": transcript,
                "words": word_list,
            })

    return segments


def classify_riva_error(exc: Any) -> str:
    """Map a gRPC / Riva exception to a clear, user-facing message.

    Duck-typed: if ``exc`` has a ``.code()`` method whose ``str()`` value
    contains a known gRPC status name, return a human-readable message;
    otherwise fall through to a generic stringified message. Never raises.
    """
    code_str = ""
    details_str = ""
    try:
        code_str = str(exc.code())
    except Exception:  # noqa: BLE001
        pass
    try:
        details_str = str(exc.details())
    except Exception:  # noqa: BLE001
        pass

    if "UNAUTHENTICATED" in code_str or "PERMISSION_DENIED" in code_str:
        return (
            "NVIDIA API key is invalid or missing. Get a free key at "
            "build.nvidia.com -> Nemotron ASR Streaming -> Get API Key, "
            f"then paste it in Advanced > Backend. [{code_str}] {details_str}"
        ).strip()
    if "RESOURCE_EXHAUSTED" in code_str:
        return (
            "NVIDIA free-tier quota reached for this API key. Wait for the "
            "quota to reset, or check your usage at build.nvidia.com. "
            f"[{code_str}] {details_str}"
        ).strip()
    if "UNAVAILABLE" in code_str:
        return (
            "NVIDIA Riva ASR servers are unreachable (offline or blocked). "
            f"Check your network and retry. [{code_str}] {details_str}"
        ).strip()
    if "INVALID_ARGUMENT" in code_str:
        return (
            "NVIDIA ASR rejected the audio or configuration (bad format, "
            "unsupported language code, etc.). "
            f"[{code_str}] {details_str}"
        ).strip()
    # Generic fallback.
    return f"NVIDIA ASR error: {exc}"


# ---------------------------------------------------------------- backend


class NvidiaAsrBackend(Backend):
    """NVIDIA Nemotron 3.5 ASR cloud transcription backend.

    Stateless apart from the API key / server config read from config at
    load(). Each transcribe_to_segments call decodes the audio to 16 kHz
    mono PCM WAV chunks, streams each chunk to NVCF, and stitches the
    chunk-relative timestamps onto the global timeline.

    The nvidia-riva-client gRPC package is NOT bundled; it is installed on
    first use via core.optional_deps.
    """

    name = "nvidia_asr"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config
        self._api_key: str = ""
        self._server: str = NVIDIA_SERVER
        self._function_id: str = NVIDIA_FUNCTION_ID
        self._chunk_seconds: float = DEFAULT_CHUNK_SECONDS
        self._language: str = ""
        self._error: str | None = None
        self._ready = False
        self._lock = threading.Lock()
        # Cached ASRService and Auth — built once per transcription worker.
        self._asr: Any = None

    # -- lifecycle -----------------------------------------------------------

    def _cfg(self) -> dict[str, Any]:
        return self._config if self._config is not None else load_config()

    def load(
        self,
        status_cb: Callable[[str], None] | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> bool:
        self._ready = False
        self._error = None
        self._asr = None
        cfg = self._cfg()
        self._api_key = str(cfg.get("nvidia_asr_api_key") or "").strip()
        self._server = str(cfg.get("nvidia_asr_server") or NVIDIA_SERVER).strip() or NVIDIA_SERVER
        self._function_id = (
            str(cfg.get("nvidia_asr_function_id") or NVIDIA_FUNCTION_ID).strip()
            or NVIDIA_FUNCTION_ID
        )
        try:
            self._chunk_seconds = float(cfg.get("nvidia_asr_chunk_seconds") or DEFAULT_CHUNK_SECONDS)
        except (TypeError, ValueError):
            self._chunk_seconds = DEFAULT_CHUNK_SECONDS
        self._language = str(cfg.get("nvidia_asr_language") or "").strip()

        if not self._api_key:
            self._error = (
                "No NVIDIA API key set — get a free key at build.nvidia.com "
                "(Nemotron ASR Streaming -> Get API Key) and paste it in "
                "Advanced > Backend."
            )
            if status_cb:
                status_cb(self._error)
            return False

        # Do NOT import riva at load — stay offline-safe and fast.
        # The key is validated on the first real transcription request.
        self._ready = True
        if status_cb:
            status_cb("NVIDIA Nemotron ASR ready.")
        if progress_cb:
            progress_cb({
                "phase": "loaded",
                "status": "NVIDIA ASR backend ready",
                "percent": 100,
                "detail": "Nemotron 3.5 ASR",
            })
        return True

    def is_ready(self) -> bool:
        return self._ready

    def get_error(self) -> str | None:
        return self._error

    # -- transcription -------------------------------------------------------

    def transcribe_to_segments(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        want_words: bool = False,
        vad_parameters: dict[str, Any] | None = None,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
        batch_size: int = 16,
        progress_cb: Callable[[int], None] | None = None,
        log_cb: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        paused: Callable[[], bool] | None = None,
        duration: float = 0.0,
    ) -> tuple[list[dict[str, Any]], LanguageInfo]:
        with self._lock:
            if not self.is_ready() and not self.load(log_cb):
                raise RuntimeError(self._error or "NVIDIA ASR backend not ready")
        if not self._api_key:
            raise RuntimeError(
                self._error or "No NVIDIA API key set for the NVIDIA ASR backend."
            )

        # Lazy-import nvidia-riva-client; install on demand when absent.
        try:
            import riva.client  # type: ignore
        except ImportError:
            try:
                from .. import optional_deps
                if log_cb:
                    log_cb("NVIDIA ASR: installing nvidia-riva-client (one-time)...")
                optional_deps.install("nvidia_asr", log_cb)
                import riva.client  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "Could not import nvidia-riva-client even after an on-demand "
                    "install attempt. Check your internet connection or install "
                    "manually: pip install nvidia-riva-client. "
                    f"Details: {e}"
                ) from e

        # Resolve duration for chunk planning.
        effective_duration = duration
        if effective_duration <= 0:
            try:
                from ..transcriber import get_duration
                effective_duration = float(get_duration(audio_path) or 0.0)
            except Exception:  # noqa: BLE001
                effective_duration = 0.0
            if log_cb and effective_duration > 0:
                log_cb(
                    f"NVIDIA ASR: probed duration {effective_duration:.0f}s "
                    "for chunk planning."
                )

        chunks = plan_chunks(
            effective_duration, self._chunk_seconds, chunk_when_unknown=True
        )
        total = len(chunks)

        # Resolve locale once for all chunks.
        locale = normalize_language_code(language or self._language)

        if log_cb:
            log_cb(
                f"NVIDIA ASR: streaming {total} chunk(s) to NVIDIA Riva "
                f"(locale {locale}). Audio leaves this machine."
            )

        # Build or reuse the ASRService.
        if self._asr is None:
            try:
                auth = riva.client.Auth(  # type: ignore[attr-defined]
                    use_ssl=True,
                    uri=self._server,
                    metadata_args=[
                        ["function-id", self._function_id],
                        ["authorization", "Bearer " + self._api_key],
                    ],
                )
                self._asr = riva.client.ASRService(auth)  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"Could not initialise NVIDIA Riva ASRService: {exc}"
                ) from exc

        all_segments: list[dict[str, Any]] = []
        duration_unknown = effective_duration <= 0

        for idx, (chunk_start, chunk_end) in enumerate(chunks):
            if cancelled and cancelled():
                if log_cb:
                    log_cb("Task cancelled")
                break
            while paused and paused() and not (cancelled and cancelled()):
                time.sleep(0.2)

            wav_path = _encode_chunk_wav(audio_path, chunk_start, chunk_end)
            try:
                # Unknown-length: stop once we slice past EOF (empty WAV).
                if duration_unknown and idx > 0:
                    try:
                        wav_size = os.path.getsize(wav_path)
                    except OSError:
                        wav_size = 0
                    # An empty past-EOF slice decodes to just the WAV header;
                    # a real chunk is far larger (see _EMPTY_WAV_BYTES).
                    if wav_size < _EMPTY_WAV_BYTES:
                        if log_cb:
                            log_cb(
                                "NVIDIA ASR: reached end of file "
                                f"after {idx} chunk(s)."
                            )
                        break

                cfg_obj = riva.client.RecognitionConfig(  # type: ignore[attr-defined]
                    encoding=riva.client.AudioEncoding.LINEAR_PCM,  # type: ignore[attr-defined]
                    sample_rate_hertz=16000,
                    audio_channel_count=1,
                    language_code=locale,
                    max_alternatives=1,
                    enable_automatic_punctuation=True,
                    enable_word_time_offsets=True,
                )
                streaming_cfg = riva.client.StreamingRecognitionConfig(  # type: ignore[attr-defined]
                    config=cfg_obj,
                    interim_results=False,
                )
                audio_chunks = riva.client.AudioChunkFileIterator(  # type: ignore[attr-defined]
                    wav_path,
                    chunk_n_frames=1600,
                )
                try:
                    responses = self._asr.streaming_response_generator(
                        audio_chunks=audio_chunks,
                        streaming_config=streaming_cfg,
                    )
                    # Materialise the stream HERE so a gRPC error (bad key,
                    # quota exhausted, server unreachable) surfaces to the
                    # classifier below. If we instead handed the lazy generator
                    # straight to results_to_segments, its defensive
                    # ``list(results)`` guard would swallow that error and the
                    # chunk would look like "0 segments" — hiding an auth /
                    # quota failure as a silent empty transcript. The pure
                    # parser then only ever sees a concrete list.
                    response_list = list(responses)
                except Exception as exc:  # noqa: BLE001
                    # Classify gRPC / Riva errors into a clear user message.
                    raise RuntimeError(classify_riva_error(exc)) from exc
                seg = results_to_segments(response_list)

            finally:
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

            seg = offset_segments(seg, chunk_start)
            all_segments.extend(seg)

            if progress_cb:
                progress_cb(min(100, int(((idx + 1) / max(total, 1)) * 100)))
            if log_cb:
                log_cb(
                    f"NVIDIA ASR: chunk {idx + 1}/{total} -> "
                    f"{len(seg)} segment(s)."
                )

        if want_words:
            for s in all_segments:
                s.setdefault("words", [])

        detected = language or self._language or ""
        return all_segments, LanguageInfo(
            language=detected, probability=1.0 if detected else 0.0
        )


# ---------------------------------------------------------------- helpers


def _encode_chunk_wav(
    audio_path: str, start_seconds: float, end_seconds: float
) -> str:
    """Decode ``audio_path[start:end]`` to a temp 16 kHz mono PCM-s16le WAV.

    Uses the bundled ffmpeg (same approach as the cloud_stt backend) so the
    NVIDIA ASR backend accepts every format the other backends do. Returns
    the temp file path; the caller deletes it.
    ``end_seconds <= start_seconds`` means "to end of file".
    """
    from ..paths import bundled_binary

    fd, out_path = tempfile.mkstemp(prefix="nvidiaasr-", suffix=CHUNK_EXT)
    os.close(fd)

    ffmpeg = bundled_binary("ffmpeg")
    cmd = [ffmpeg, "-nostdin", "-loglevel", "error", "-y"]
    if start_seconds > 0:
        cmd += ["-ss", f"{start_seconds:.3f}"]
    cmd += ["-i", audio_path]
    if end_seconds > start_seconds:
        cmd += ["-t", f"{end_seconds - start_seconds:.3f}"]
    cmd += ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", out_path]

    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "check": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.run(cmd, **kwargs)
    except (FileNotFoundError, OSError) as e:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        raise RuntimeError(
            "ffmpeg is required to prepare audio for the NVIDIA ASR backend "
            "but was not found. Use the default engine, or install ffmpeg."
        ) from e
    except subprocess.CalledProcessError as e:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        detail = (e.stderr or b"").decode("utf-8", "replace").strip()[-400:]
        raise RuntimeError(
            "ffmpeg could not prepare this file for the NVIDIA ASR backend "
            "(it may be corrupt or an unsupported format): "
            f"{detail or 'no error output'}"
        ) from e
    return out_path
