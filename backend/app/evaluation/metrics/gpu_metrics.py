"""Phase 25 — GPU profiling utility. Degrades gracefully when GPU unavailable."""
from __future__ import annotations

import logging
import subprocess

from backend.app.evaluation.schemas import GPUProfileResult

logger = logging.getLogger(__name__)


def profile_gpu(model_loaded: bool = False, batch_size: int | None = None) -> GPUProfileResult:
    """
    Capture GPU state. Returns degraded profile if GPU or nvidia-smi unavailable.
    """
    result = GPUProfileResult(model_loaded=model_loaded, batch_size=batch_size)

    try:
        import torch
        if not torch.cuda.is_available():
            result.gpu_available = False
            result.profiling_degraded = True
            result.degradation_reason = "CUDA not available"
            return result

        result.gpu_available = True
        result.gpu_name = torch.cuda.get_device_name(0)
        result.cuda_version = torch.version.cuda
        result.torch_cuda_version = str(torch.__version__)
        result.memory_allocated_mb = round(torch.cuda.memory_allocated() / 1024 / 1024, 2)
        result.memory_reserved_mb = round(torch.cuda.memory_reserved() / 1024 / 1024, 2)
        result.peak_memory_mb = round(torch.cuda.max_memory_allocated() / 1024 / 1024, 2)
    except ImportError:
        result.gpu_available = False
        result.profiling_degraded = True
        result.degradation_reason = "PyTorch not installed"
        return result
    except Exception as exc:
        result.profiling_degraded = True
        result.degradation_reason = f"torch GPU query failed: {exc}"

    # nvidia-smi for utilization
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            util_str = proc.stdout.strip()
            if util_str:
                result.utilization_percent = float(util_str.splitlines()[0].strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        logger.debug("nvidia-smi unavailable for utilization — skipping")

    return result


def reset_gpu_peak_memory() -> None:
    """Reset peak memory tracker between profiling runs."""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass
