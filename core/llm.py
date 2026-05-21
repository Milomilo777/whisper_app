"""Local LLM panel — Qwen2.5-1.5B-Instruct via llama-cpp-python.

The AI Layer (v0.8 Phase 2) provides offline post-processing of a
finished transcript:

  * **Summarise**  — bullet-point digest of the conversation.
  * **Action items** — extracted as a JSON list (GBNF-constrained).
  * **Ask question** — single-turn Q&A scoped to the transcript.
  * **Translate**  — language-pair translation through the LLM, so
    we don't need a separate NLLB model.

Design choices:

  * **Download-on-first-use**, NOT bundled. Qwen2.5-1.5B Q4_K_M is
    ~1 GB; bundling pushes Portable from 450 MB → 1.45 GB. Instead
    a one-click "Enable AI features" button downloads the model
    into ``user_cache_dir()/llm/``. The wizard reports
    :func:`is_model_present` so the UI can show "Install AI model"
    vs "Ready" states.
  * **Lazy import** of llama-cpp-python so the module is safe to
    import even when the optional dep isn't installed.
  * **Singleton model** — ``LLMRunner`` keeps one llama_cpp.Llama
    instance to avoid the multi-second reload cost on every call.

When ``llama-cpp-python`` isn't installed, every public function
either returns ``None`` / raises :class:`LLMUnavailable` so the UI
can swap to a "feature off" placeholder. No silent partial work.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import user_cache_dir

logger = logging.getLogger(__name__)


DEFAULT_MODEL_NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
DEFAULT_MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
    "resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
)
DEFAULT_MODEL_SIZE_BYTES = 1_117_000_000  # ~1.04 GB; tolerance check only


# ---------------------------------------------------------------- availability


class LLMUnavailable(RuntimeError):
    """Raised when llama-cpp-python isn't installed."""


def runtime_available() -> bool:
    """True iff llama-cpp-python imports cleanly."""
    try:
        import llama_cpp  # type: ignore[import-not-found] # noqa: F401
    except ImportError:
        return False
    return True


def runtime_availability_reason() -> str:
    if runtime_available():
        return ""
    return (
        "llama-cpp-python not installed — `pip install llama-cpp-python` "
        "to enable AI features."
    )


# ---------------------------------------------------------------- model file


def model_dir() -> Path:
    return user_cache_dir() / "llm"


def default_model_path() -> Path:
    return model_dir() / DEFAULT_MODEL_NAME


def is_model_present(path: Path | None = None) -> bool:
    """True iff the model file exists and looks sane (≥ 100 MB)."""
    p = path if path is not None else default_model_path()
    if not p.exists():
        return False
    try:
        return p.stat().st_size > 100_000_000
    except OSError:
        return False


def download_default_model(
    *,
    log: Callable[[str], None] | None = None,
    url: str = DEFAULT_MODEL_URL,
    dest: Path | None = None,
    chunk_size: int = 1 << 20,
    cancel_event: threading.Event | None = None,
) -> str:
    """Download the LLM model to ``model_dir()`` atomically.

    Writes to ``<dest>.part`` and ``os.replace``s on success so a
    partial download (network drop, user-cancel) never leaves the
    user with a half-broken model file. Returns the absolute path.

    Idempotent: a full pre-existing file is detected via size sanity
    check and skipped.
    """
    dest = dest if dest is not None else default_model_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_model_present(dest):
        if log:
            log(f"LLM model already present at {dest}")
        return str(dest)
    part = dest.with_suffix(dest.suffix + ".part")
    if part.exists():
        try:
            part.unlink()
        except OSError:
            pass
    if log:
        log(f"Downloading LLM model from {url} → {dest} (~1 GB)…")
    req = urllib.request.Request(url, headers={"User-Agent": "WhisperProject/0.8"})
    started = time.time()
    bytes_done = 0
    cancelled = False
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("content-length") or 0)
            with open(part, "wb") as f:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        cancelled = True
                        break
                    chunk = r.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_done += len(chunk)
                    if log and total:
                        pct = int(bytes_done / total * 100)
                        if pct % 5 == 0:
                            log(f"  …{pct}% ({bytes_done/1e9:.2f} / {total/1e9:.2f} GB)")
    except Exception:
        # File handle now closed by `with`; safe to unlink the
        # partial download before re-raising. Windows in particular
        # refuses os.unlink on a handle that's still open, so we
        # MUST exit the with-block first.
        try:
            os.unlink(part)
        except OSError:
            pass
        raise
    if cancelled:
        try:
            os.unlink(part)
        except OSError:
            pass
        raise RuntimeError("LLM download cancelled")
    os.replace(part, dest)
    if log:
        elapsed = time.time() - started
        log(f"LLM model ready at {dest} (in {elapsed:.1f}s)")
    return str(dest)


# ---------------------------------------------------------------- runner


@dataclass
class LLMConfig:
    model_path: str
    n_ctx: int = 4096
    n_threads: int = 0  # 0 means default = os.cpu_count()
    n_gpu_layers: int = 0  # CPU-only by default; user can boost
    seed: int = 42


class LLMRunner:
    """Wraps a single llama_cpp.Llama instance.

    Cheap to instantiate (no model load). Call :meth:`load` to
    actually create the underlying Llama; first prompt after load
    pays the JIT cost.
    """

    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg
        self._llama: Any = None
        self._lock = threading.Lock()

    def is_loaded(self) -> bool:
        return self._llama is not None

    def load(self) -> None:
        if self._llama is not None:
            return
        if not runtime_available():
            raise LLMUnavailable(runtime_availability_reason())
        if not Path(self.cfg.model_path).exists():
            raise FileNotFoundError(
                f"LLM model file missing: {self.cfg.model_path}. "
                "Download it via the Advanced dialog's 'Install AI model' button."
            )
        from llama_cpp import Llama  # type: ignore[import-not-found]
        kwargs: dict[str, Any] = {
            "model_path": self.cfg.model_path,
            "n_ctx": self.cfg.n_ctx,
            "n_gpu_layers": self.cfg.n_gpu_layers,
            "seed": self.cfg.seed,
            "verbose": False,
        }
        if self.cfg.n_threads > 0:
            kwargs["n_threads"] = self.cfg.n_threads
        self._llama = Llama(**kwargs)

    def unload(self) -> None:
        with self._lock:
            self._llama = None

    def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> str:
        """Run one chat completion. Caller holds the lock."""
        with self._lock:
            self.load()
            assert self._llama is not None
            out = self._llama.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        try:
            return str(out["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            return ""

    # ---------- task-specific entry points -------------------------

    def summarise(self, transcript_text: str, *, max_bullets: int = 8) -> str:
        """Bullet-point summary of the transcript."""
        prompt = (
            f"Summarise the following transcript in at most {max_bullets} "
            "concise bullet points. Keep proper names and technical terms "
            "verbatim. Do not invent details that aren't in the source.\n\n"
            f"Transcript:\n\"\"\"\n{transcript_text}\n\"\"\""
        )
        return self._chat(
            [{"role": "user", "content": prompt}],
            max_tokens=600,
        )

    def action_items(self, transcript_text: str) -> list[str]:
        """Pull out action items as a JSON list of strings.

        We ask the model for strict JSON; if parsing fails we return
        an empty list rather than guessing — the UI surfaces that
        as "no action items detected".
        """
        prompt = (
            "Extract the actionable to-do items from this transcript. "
            "Respond ONLY with a JSON array of strings. If there are "
            "no actions, respond with []. Do not include any prose.\n\n"
            f"Transcript:\n\"\"\"\n{transcript_text}\n\"\"\""
        )
        raw = self._chat(
            [{"role": "user", "content": prompt}],
            max_tokens=400,
        )
        return _parse_json_list(raw)

    def ask(self, transcript_text: str, question: str) -> str:
        prompt = (
            "Answer the question using ONLY information from the transcript "
            "below. If the answer isn't in the transcript, say "
            "\"Not in transcript.\"\n\n"
            f"Transcript:\n\"\"\"\n{transcript_text}\n\"\"\"\n\n"
            f"Question: {question}"
        )
        return self._chat(
            [{"role": "user", "content": prompt}],
            max_tokens=400,
        )

    def translate(
        self, text: str, *, target_language: str = "English"
    ) -> str:
        prompt = (
            f"Translate the following text into {target_language}. "
            "Preserve proper names and technical terms verbatim. "
            "Respond with only the translation, no explanations.\n\n"
            f"\"\"\"\n{text}\n\"\"\""
        )
        return self._chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max(256, int(len(text.split()) * 1.5)),
        )


def _parse_json_list(raw: str) -> list[str]:
    """Best-effort JSON-array parse of an LLM response.

    Strips common chat-style wrappers (markdown fences, leading
    explanatory text) before parsing. Returns ``[]`` on any error.
    """
    if not raw:
        return []
    text = raw.strip()
    # Strip ```json ... ``` fences if present.
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop the opening fence + optional language tag.
        lines = lines[1:]
        # Drop the closing fence.
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Trim leading non-JSON prose by finding the first '[' that
    # opens the array.
    if not text.startswith("["):
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if isinstance(item, (str, int, float))]
