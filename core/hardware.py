"""Hardware autodetect — probe, persist, and load the chosen tier.

This module is the data-access layer the Hardware Wizard UI sits on
top of. It MUST stay Tk-free so ``core.transcriber.detect_device``
can call :func:`load_hardware_choice` without dragging tkinter into
the worker subprocess.

Tier probe order (best → worst):

  CUDA float16 → CUDA int8_float16 → QNN NPU (Snapdragon) →
  Intel NPU (OpenVINO) → OpenVINO GPU → DirectML →
  faster-whisper CPU int8

For each detected tier the wizard records:

  * ``slug``        — stable identifier (``cuda_float16``)
  * ``label``       — human description for the UI
  * ``device``      — what to pass to ``WhisperModel(device=...)``
  * ``compute_type``— matching ``compute_type`` argument
  * ``backend``     — ``faster_whisper`` for the bundled engine; one
    of the other tier slugs when the user has to switch backends to
    actually use it (we still surface the tier so they know it's
    possible)
  * ``detail``      — free-form text (GPU model, OpenVINO device id)

The chosen tier is persisted as ``hardware.json`` next to the rest
of the user data so it survives reinstall + roams with a profile.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .config import user_data_dir


logger = logging.getLogger(__name__)


HARDWARE_FILE_NAME = "hardware.json"
HARDWARE_FILE_VERSION = 1


@dataclass(frozen=True)
class Tier:
    slug: str
    label: str
    device: str
    compute_type: str
    backend: str = "faster_whisper"
    detail: str = ""


def hardware_json_path() -> Path:
    return user_data_dir() / HARDWARE_FILE_NAME


# ---------------------------------------------------------------- probes


def _gpu_name() -> str:
    """Best-effort NVIDIA GPU name; empty string when unknown."""
    try:
        import torch  # type: ignore[import-not-found]
        if torch.cuda.is_available():
            return str(torch.cuda.get_device_name(0))
    except Exception:  # noqa: BLE001
        pass
    return "NVIDIA GPU"


def _cpu_name() -> str:
    try:
        import platform
        return platform.processor() or platform.machine() or "CPU"
    except Exception:  # noqa: BLE001
        return "CPU"


def _probe_cuda() -> list[Tier]:
    """Return ordered list of CUDA-backed tiers actually supported.

    ``ctranslate2.contains_cuda_device()  # type: ignore[attr-defined]`` is the official-blessed
    probe; ``torch.cuda.is_available()`` is the fallback when ct2
    is not on the system (older builds). We never raise — a missing
    CUDA stack is the common case.
    """
    try:
        import ctranslate2  # type: ignore[import-not-found]
        if not ctranslate2.contains_cuda_device():  # type: ignore[attr-defined]
            return []
        supported: set[str] = set()
        try:
            supported = set(ctranslate2.get_supported_compute_types("cuda"))
        except Exception:  # noqa: BLE001
            supported = {"float16"}
        gpu = _gpu_name()
        tiers: list[Tier] = []
        if "float16" in supported:
            tiers.append(Tier(
                slug="cuda_float16",
                label=f"NVIDIA CUDA (float16) — {gpu}",
                device="cuda",
                compute_type="float16",
                detail=gpu,
            ))
        if "int8_float16" in supported:
            tiers.append(Tier(
                slug="cuda_int8_float16",
                label=f"NVIDIA CUDA (int8+float16) — {gpu}",
                device="cuda",
                compute_type="int8_float16",
                detail=gpu,
            ))
        return tiers
    except Exception:  # noqa: BLE001
        return []


def _probe_qnn_npu() -> list[Tier]:
    """Snapdragon X NPU via onnxruntime QNN execution provider.

    Detected here so the wizard can show "available — switch backend
    to use" even though the bundled faster_whisper backend can't
    drive QNN directly. The user enables it by installing the matching
    backend in a future release.
    """
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]
        provs = list(ort.get_available_providers())
        if "QNNExecutionProvider" in provs:
            return [Tier(
                slug="qnn_npu",
                label="Snapdragon X NPU (QNN) — backend not bundled",
                device="cpu",
                compute_type="int8",
                backend="qnn_npu",
                detail="QNN provider detected via onnxruntime",
            )]
    except Exception:  # noqa: BLE001
        pass
    return []


def _probe_openvino() -> list[Tier]:
    """Intel NPU + Intel/AMD GPU via OpenVINO."""
    tiers: list[Tier] = []
    try:
        import openvino as ov  # type: ignore[import-not-found]
        core = ov.Core()
        devices = list(core.available_devices)
        for dev in devices:
            up = dev.upper()
            if up.startswith("NPU"):
                tiers.append(Tier(
                    slug="openvino_npu",
                    label=f"Intel NPU (OpenVINO {dev}) — backend not bundled",
                    device="cpu",
                    compute_type="int8",
                    backend="openvino_npu",
                    detail=f"OpenVINO device {dev}",
                ))
            elif up.startswith("GPU"):
                tiers.append(Tier(
                    slug="openvino_gpu",
                    label=f"GPU via OpenVINO ({dev}) — backend not bundled",
                    device="cpu",
                    compute_type="int8",
                    backend="openvino_gpu",
                    detail=f"OpenVINO device {dev}",
                ))
    except Exception:  # noqa: BLE001
        pass
    return tiers


def _probe_directml() -> list[Tier]:
    """DirectML execution provider — Windows GPU path for AMD/Intel."""
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]
        provs = list(ort.get_available_providers())
        if "DmlExecutionProvider" in provs:
            return [Tier(
                slug="directml",
                label="DirectML GPU (Windows DX12) — backend not bundled",
                device="cpu",
                compute_type="int8",
                backend="directml",
                detail="DML provider detected via onnxruntime",
            )]
    except Exception:  # noqa: BLE001
        pass
    return []


def _probe_cpu() -> list[Tier]:
    cpu = _cpu_name()
    return [Tier(
        slug="cpu_int8",
        label=f"CPU int8 (universal fallback) — {cpu}",
        device="cpu",
        compute_type="int8",
        detail=cpu,
    )]


def probe_tiers() -> list[Tier]:
    """Return every tier the current host supports, best → worst.

    CPU int8 is always last and always present so the list is never
    empty; callers can rely on ``tiers[-1]`` as a guaranteed fallback.
    """
    tiers: list[Tier] = []
    tiers.extend(_probe_cuda())
    tiers.extend(_probe_qnn_npu())
    tiers.extend(_probe_openvino())
    tiers.extend(_probe_directml())
    tiers.extend(_probe_cpu())
    return tiers


def first_supported_tier(tiers: list[Tier]) -> Tier:
    """Pick the highest-ranked tier the bundled faster_whisper backend
    can actually drive today. Non-FW tiers (QNN / OpenVINO / DirectML)
    are surfaced in the UI but not auto-selected.
    """
    for t in tiers:
        if t.backend == "faster_whisper":
            return t
    return tiers[-1]


# ---------------------------------------------------------------- persistence


def save_hardware_choice(
    tier: Tier,
    *,
    benchmark_rtf: float | None = None,
) -> Path:
    """Write ``hardware.json`` atomically and return the path."""
    payload: dict[str, Any] = {
        "version": HARDWARE_FILE_VERSION,
        "detected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tier": tier.slug,
        "tier_label": tier.label,
        "device": tier.device,
        "compute_type": tier.compute_type,
        "backend": tier.backend,
        "benchmark_rtf": benchmark_rtf,
        "hardware_summary": tier.detail,
    }
    path = hardware_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    logger.info(
        "hardware.json saved: tier=%s device=%s compute_type=%s",
        tier.slug, tier.device, tier.compute_type,
    )
    return path


def load_hardware_choice() -> dict[str, Any] | None:
    """Read ``hardware.json``; return None on any error.

    A bad file is renamed to ``.corrupt`` so the auto-probe path can
    recreate it cleanly on the next wizard run, mirroring the
    config.json corruption handling.
    """
    path = hardware_json_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("hardware.json is not a JSON object")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        logger.warning("Could not read %s (%s); ignoring", path, e)
        try:
            os.replace(path, str(path) + ".corrupt")
        except OSError:
            pass
        return None
    return data


def device_choice_from_hardware_file() -> tuple[str, str] | None:
    """Return ``(device, compute_type)`` from ``hardware.json``, or None.

    Used by :func:`core.transcriber.detect_device` to honour the
    wizard's persisted choice before falling back to the auto-probe.
    Returns None when:

      * the file is missing or unreadable
      * the recorded tier is for a non-bundled backend
      * the wizard picked CUDA but the current process can no longer
        see a CUDA device (laptop dock unplug, driver uninstall)
    """
    data = load_hardware_choice()
    if not data:
        return None
    device = str(data.get("device") or "").strip()
    compute_type = str(data.get("compute_type") or "").strip()
    if not device or not compute_type:
        return None
    backend = str(data.get("backend") or "faster_whisper")
    if backend != "faster_whisper":
        return None
    if device == "cuda":
        try:
            import ctranslate2  # type: ignore[import-not-found]
            if not ctranslate2.contains_cuda_device():  # type: ignore[attr-defined]
                logger.info(
                    "hardware.json picks CUDA but ctranslate2 no longer "
                    "sees a CUDA device; falling back to auto-probe."
                )
                return None
        except Exception:  # noqa: BLE001
            return None
    return device, compute_type


def tier_to_dict(tier: Tier) -> dict[str, Any]:
    """Dataclass → dict for tests and serialization."""
    return asdict(tier)
