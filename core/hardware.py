"""Pick the best ``(device, compute_type)`` for the current host.

Resolution chain — first match wins, every choice is logged:

  1. Explicit ``config["device"]`` (anything other than ``"auto"``).
  2. ``ctranslate2.contains_cuda_device()`` probe → ``cuda`` + the
     best compute_type the CUDA build supports.
  3. ``torch.cuda.is_available()`` probe (legacy fallback).
  4. CPU + the configured ``compute_type`` (defaults to ``int8``).

Tk-free so the worker subprocess can call this without dragging
tkinter into the import graph.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def detect_device_for(config: dict[str, Any]) -> tuple[str, str]:
    """Return ``(device, compute_type)`` for a given config dict."""
    if config.get("device") != "auto":
        dev = str(config.get("device", "cpu"))
        ct = str(config.get("compute_type", "int8"))
        logger.info(
            "device_choice device=%s compute_type=%s source=config", dev, ct,
        )
        return dev, ct
    try:
        import ctranslate2  # type: ignore[import-not-found]
        if ctranslate2.contains_cuda_device():  # type: ignore[attr-defined]
            try:
                supported = set(
                    ctranslate2.get_supported_compute_types("cuda")
                )
            except Exception:  # noqa: BLE001
                supported = {"float16"}
            for ct in ("float16", "int8_float16", "int8"):
                if ct in supported:
                    logger.info(
                        "device_choice device=cuda compute_type=%s "
                        "source=ctranslate2_probe", ct,
                    )
                    return "cuda", ct
    except (ImportError, AttributeError, RuntimeError):
        pass
    try:
        import torch  # type: ignore[import-not-found]
        if torch.cuda.is_available():
            logger.info(
                "device_choice device=cuda compute_type=float16 "
                "source=torch_probe"
            )
            return "cuda", "float16"
    except (ImportError, AttributeError):
        pass
    ct = str(config.get("compute_type", "int8"))
    logger.info(
        "device_choice device=cpu compute_type=%s source=cpu_fallback", ct,
    )
    return "cpu", ct
