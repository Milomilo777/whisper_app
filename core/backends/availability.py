"""Engine picker registry + cheap availability probes.

Single source of truth shared by the Transcribe-tab engine picker and the
Advanced dialog's backend combobox, so the two never drift. Also resolves the
*effective default* engine: a trusted build that ships a Google Cloud
service-account key (``creds/gcloud_stt.json``) defaults to cloud STT so it
works out of the box, while a plain source checkout stays fully offline on
faster-whisper.

Pure: no Tkinter, no network. The import-based runtime probes are cheap when a
dependency is missing (ImportError fires immediately) but can be slow when a
heavy native lib IS installed, so GUI callers should compute cloud-engine
statuses lazily (on selection / dialog open) rather than eagerly at every
startup — see the ``deep`` flag on :func:`engine_status`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

# (friendly label, transcribe_backend value) — also the display order. Offline
# engines stay first; the two cloud options spell out their auth model so a
# non-technical user can tell them apart (a pasted key vs a downloaded file).
ENGINE_CHOICES: list[tuple[str, str]] = [
    ("Faster-Whisper — offline, default", "faster_whisper"),
    ("whisper.cpp — offline, low-end CPUs", "whisper_cpp"),
    ("Parakeet — offline, NVIDIA", "parakeet"),
    ("Gemini cloud — simple API key", "cloud_stt"),
    (
        "Google Cloud Speech-to-Text — service account (60 min/mo free)",
        "google_cloud_stt",
    ),
]
LABEL_TO_VALUE: dict[str, str] = {label: value for label, value in ENGINE_CHOICES}
VALUE_TO_LABEL: dict[str, str] = {value: label for label, value in ENGINE_CHOICES}
KNOWN_ENGINES: frozenset[str] = frozenset(value for _label, value in ENGINE_CHOICES)

# Where get_backend() lands when a stored value is unknown/empty.
FALLBACK_ENGINE = "faster_whisper"


def normalise_engine(value: Any) -> str:
    """Map any stored/raw backend value to a known engine, else the fallback."""
    name = str(value or "").strip().lower()
    return name if name in KNOWN_ENGINES else FALLBACK_ENGINE


# --------------------------------------------------------------- credentials


def bundled_gcloud_key_path() -> str:
    """Path to a build-bundled Google Cloud key, or ``""`` — no google libs."""
    try:
        from .google_cloud_stt import bundled_credentials_path

        return bundled_credentials_path()
    except Exception:  # noqa: BLE001
        return ""


def gcloud_key_path(cfg: Mapping[str, Any]) -> str:
    """The credentials path Google Cloud STT would actually use.

    The user-selected JSON if it is set and present on disk, else the
    build-bundled key, else ``""``. Pure filesystem checks — no google libs.
    """
    explicit = str(cfg.get("gcloud_stt_credentials_json") or "").strip()
    if explicit and os.path.isfile(explicit):
        return explicit
    return bundled_gcloud_key_path()


def has_gcloud_key(cfg: Mapping[str, Any]) -> bool:
    """True iff Google Cloud STT has a usable service-account key available."""
    return bool(gcloud_key_path(cfg))


def default_engine(cfg: Mapping[str, Any] | None = None) -> str:
    """The engine to use when the user has not chosen one.

    A trusted build that ships (or a user who has configured) a Google Cloud
    key defaults to ``google_cloud_stt`` so cloud STT works immediately;
    otherwise stay offline on faster-whisper.
    """
    if has_gcloud_key(cfg or {}):
        return "google_cloud_stt"
    return FALLBACK_ENGINE


# --------------------------------------------------------------- availability


@dataclass(frozen=True)
class EngineStatus:
    """Whether one engine can transcribe right now.

    ``ready``  — usable immediately with the current config/install.
    ``detail`` — short human note: the blocking reason when not ready, or an
                 informational hint (e.g. a pending download) when ready.
    """

    value: str
    ready: bool
    detail: str = ""


def _faster_whisper_model_present(cfg: Mapping[str, Any]) -> bool:
    """Mirror App._model_bytes_present without importing the heavy backend."""
    try:
        from pathlib import Path

        from core.hub import default_hub_folder, model_folder_for

        mp = str(cfg.get("model_path") or "").strip()
        if mp and Path(mp).exists():
            return True
        model_info = cfg.get("model") or {}
        name = ""
        if isinstance(model_info, dict):
            name = str(model_info.get("name") or "").strip()
        if not name:
            name = str(cfg.get("whisper_model") or "").strip()
        if not name:
            name = "faster-whisper-large-v3"
        hub = str(cfg.get("hub_folder") or "").strip() or str(default_hub_folder())
        return model_folder_for(hub, name).exists()
    except Exception:  # noqa: BLE001
        return False


def _faster_whisper_status(cfg: Mapping[str, Any]) -> EngineStatus:
    """Cheap status: model presence only — no heavy import (startup-safe)."""
    present = _faster_whisper_model_present(cfg)
    detail = "" if present else "model downloads on first run (~3 GB)"
    return EngineStatus("faster_whisper", True, detail)


def _faster_whisper_status_deep(cfg: Mapping[str, Any]) -> EngineStatus:
    """Honest readiness: the model must already be on disk AND the
    ``faster_whisper`` package must import cleanly.

    Unlike the cheap probe (which always reports ``ready=True`` because the
    model can download on first run), the deep probe is meant to answer
    "can I transcribe right now, with no extra wait/setup" — so a
    not-yet-downloaded model is reported as NOT ready.
    """
    try:
        import faster_whisper  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return EngineStatus(
            "faster_whisper", False, f"faster-whisper not installed ({e})"
        )
    if not _faster_whisper_model_present(cfg):
        return EngineStatus("faster_whisper", False, "Model not downloaded yet")
    return EngineStatus("faster_whisper", True, "")


def _whisper_cpp_status(cfg: Mapping[str, Any]) -> EngineStatus:
    try:
        from . import whisper_cpp

        if whisper_cpp.is_available():
            return EngineStatus("whisper_cpp", True, "")
        return EngineStatus("whisper_cpp", False, whisper_cpp.availability_reason())
    except Exception as e:  # noqa: BLE001
        return EngineStatus("whisper_cpp", False, str(e) or "unavailable")


def _parakeet_status(cfg: Mapping[str, Any]) -> EngineStatus:
    try:
        from . import parakeet

        reason = parakeet.availability_reason()
        return EngineStatus("parakeet", not reason, reason)
    except Exception as e:  # noqa: BLE001
        return EngineStatus("parakeet", False, str(e) or "unavailable")


def _cloud_stt_status(cfg: Mapping[str, Any]) -> EngineStatus:
    if str(cfg.get("cloud_stt_api_key") or "").strip():
        return EngineStatus("cloud_stt", True, "")
    return EngineStatus(
        "cloud_stt", False, "paste a Gemini API key in Advanced settings"
    )


def _google_cloud_stt_status(cfg: Mapping[str, Any]) -> EngineStatus:
    have_key = has_gcloud_key(cfg)
    try:
        from . import google_cloud_stt as gcs

        runtime = gcs.runtime_available()
    except Exception:  # noqa: BLE001
        runtime = False
    if not runtime:
        return EngineStatus(
            "google_cloud_stt",
            False,
            "Google Cloud client not installed (installs on first use)",
        )
    if not have_key:
        return EngineStatus(
            "google_cloud_stt",
            False,
            "add a service-account JSON in Advanced settings",
        )
    return EngineStatus("google_cloud_stt", True, "")


_PROBES: dict[str, Callable[[Mapping[str, Any]], EngineStatus]] = {
    "faster_whisper": _faster_whisper_status_deep,
    "whisper_cpp": _whisper_cpp_status,
    "parakeet": _parakeet_status,
    "cloud_stt": _cloud_stt_status,
    "google_cloud_stt": _google_cloud_stt_status,
}


def engine_status(value: Any, cfg: Mapping[str, Any], *, deep: bool = True) -> EngineStatus:
    """Readiness of one engine.

    ``deep=True`` runs the honest import-based probes (used by the Advanced
    dialog + tests). ``deep=False`` is the cheap path for the always-on
    Transcribe-tab status line: it does NO heavy import at startup — cloud
    readiness keys off the credential, offline whisper.cpp/parakeet are
    assumed present (a run surfaces any gap), faster-whisper keeps its
    filesystem check.
    """
    engine = normalise_engine(value)
    if not deep:
        if engine == "google_cloud_stt":
            if has_gcloud_key(cfg):
                return EngineStatus(engine, True, "")
            return EngineStatus(
                engine, False, "add a service-account JSON in Advanced settings"
            )
        if engine == "cloud_stt":
            return _cloud_stt_status(cfg)
        if engine == "faster_whisper":
            return _faster_whisper_status(cfg)
        return EngineStatus(engine, True, "")
    probe = _PROBES.get(engine)
    return probe(cfg) if probe else EngineStatus(engine, True, "")


def engine_statuses(cfg: Mapping[str, Any]) -> dict[str, EngineStatus]:
    """Deep status of every engine, keyed by backend value (for tests/audits)."""
    return {value: _PROBES[value](cfg) for _label, value in ENGINE_CHOICES}
