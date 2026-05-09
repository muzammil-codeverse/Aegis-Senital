"""Phase 25 — System latency profiling runner."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from backend.app.evaluation.schemas import BenchmarkTaskResult
from backend.app.evaluation.metrics.latency_metrics import LatencyProfiler
from backend.app.evaluation.metrics.gpu_metrics import profile_gpu, reset_gpu_peak_memory

logger = logging.getLogger(__name__)


class SystemLatencyRunner:
    """
    Profiles end-to-end and per-stage latency on a video input.
    Does not require a live camera — accepts any cv2-readable path.
    """

    def __init__(self, device: str = "cpu", duration_seconds: int = 60) -> None:
        self.device = device
        self.duration_seconds = duration_seconds

    def run(
        self,
        input_path: str,
        run_dir: Path,
        stage_callbacks: dict[str, Any] | None = None,
    ) -> BenchmarkTaskResult:
        """
        Profile latency from a video file or stream.

        stage_callbacks: { stage_name: callable(frame) → None }
        Each callback is timed and recorded.
        """
        warnings = []
        profiler = LatencyProfiler()

        try:
            import cv2
        except ImportError:
            return BenchmarkTaskResult(
                task="latency",
                model_name="system_pipeline",
                dataset_name=input_path,
                skipped=True,
                skip_reason="OpenCV not available",
            )

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            return BenchmarkTaskResult(
                task="latency",
                model_name="system_pipeline",
                dataset_name=input_path,
                skipped=True,
                skip_reason=f"Cannot open video: {input_path}",
            )

        reset_gpu_peak_memory()
        profiler.start()
        deadline = time.monotonic() + self.duration_seconds
        stage_callbacks = stage_callbacks or {}

        try:
            while time.monotonic() < deadline:
                with profiler.measure("frame_decode"):
                    ret, frame = cap.read()
                if not ret:
                    break

                profiler.record_frame()

                import numpy as np
                with profiler.measure("preprocessing"):
                    resized = cv2.resize(frame, (640, 640))

                for stage_name, callback in stage_callbacks.items():
                    try:
                        with profiler.measure(stage_name):
                            callback(resized)
                    except Exception as exc:
                        warnings.append(f"Stage '{stage_name}' failed: {exc}")

        finally:
            cap.release()

        metric_result = profiler.compute()
        gpu_profile = profile_gpu()

        # Write latency profile JSON
        latency_out = run_dir / "latency_profile.json"
        with open(latency_out, "w", encoding="utf-8") as f:
            json.dump(metric_result.to_dict(), f, indent=2, default=str)

        # Write GPU profile JSON
        gpu_out = run_dir / "gpu_profile.json"
        with open(gpu_out, "w", encoding="utf-8") as f:
            json.dump(gpu_profile.to_dict(), f, indent=2, default=str)

        # Write latency report markdown
        self._write_latency_report(metric_result, gpu_profile, run_dir)

        return BenchmarkTaskResult(
            task="latency",
            model_name="system_pipeline",
            device=self.device,
            dataset_name=input_path,
            metrics={
                **metric_result.to_dict(),
                "gpu_profile": gpu_profile.to_dict(),
            },
            artifacts={
                "latency_profile": str(latency_out),
                "gpu_profile": str(gpu_out),
            },
            warnings=warnings + metric_result.warnings,
        )

    def _write_latency_report(self, latency, gpu, run_dir: Path) -> None:
        out = run_dir / "latency_report.md"
        lines = [
            "# Latency Profiling Report",
            "",
            f"**Duration:** {latency.duration_seconds}s  ",
            f"**Frames profiled:** {latency.total_frames_profiled}  ",
            f"**Average FPS:** {latency.avg_fps}  ",
            f"**Dropped frames:** {latency.dropped_frames}  ",
            "",
            "## Per-Stage Latency",
            "",
            "| Stage | p50 ms | p90 ms | p95 ms | p99 ms | max ms | samples |",
            "|-------|--------|--------|--------|--------|--------|---------|",
        ]
        for s in latency.stages:
            lines.append(
                f"| {s.stage} | {s.p50_ms} | {s.p90_ms} | {s.p95_ms} | {s.p99_ms} | {s.max_ms} | {s.samples} |"
            )
        lines += [
            "",
            "## GPU Profile",
            "",
            f"- Available: {gpu.gpu_available}",
            f"- Name: {gpu.gpu_name or '—'}",
            f"- CUDA: {gpu.cuda_version or '—'}",
            f"- Memory allocated: {gpu.memory_allocated_mb} MB",
            f"- Peak memory: {gpu.peak_memory_mb} MB",
            f"- Utilization: {gpu.utilization_percent}%",
            f"- Degraded: {gpu.profiling_degraded}",
        ]
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
