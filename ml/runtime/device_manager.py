from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def is_cuda_available() -> bool:
    try:
        import torch
    except Exception:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def get_best_device(prefer_gpu: bool = True, config: dict[str, Any] | None = None) -> str:
    cfg = config or {}
    if cfg.get("device") in {"cpu", "cuda"}:
        requested = str(cfg["device"])
        if requested == "cuda" and not is_cuda_available():
            if bool(cfg.get("require_gpu", False)):
                raise RuntimeError("CUDA device requested and require_gpu=true, but CUDA is unavailable")
            logger.warning("CUDA requested but unavailable; falling back to CPU")
            return "cpu"
        return requested
    if prefer_gpu and is_cuda_available():
        return "cuda"
    return "cpu"


def require_cuda_if_configured(config: dict[str, Any] | None = None) -> None:
    cfg = config or {}
    if bool(cfg.get("require_gpu", False)) and not is_cuda_available():
        raise RuntimeError("GPU is required by runtime config but CUDA is unavailable")
