"""Phase 25 — Benchmark report writer."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.app.evaluation.schemas import BenchmarkRun

logger = logging.getLogger(__name__)


class ReportWriter:
    """Writes a complete benchmark run to storage/evaluation_runs/<run_id>/."""

    def write(self, run: BenchmarkRun, run_dir: Path) -> dict[str, str]:
        """
        Write all artifacts for a benchmark run.
        Returns mapping of artifact_name → file_path.
        """
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        artifacts = {}

        # metrics.json
        metrics_path = run_dir / "metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(run.to_dict(), f, indent=2, default=str)
        artifacts["metrics_json"] = str(metrics_path)

        latency_profile = self._extract_latency_profile(run)
        latency_path = run_dir / "latency_profile.json"
        with open(latency_path, "w", encoding="utf-8") as f:
            json.dump(latency_profile, f, indent=2, default=str)
        artifacts["latency_profile_json"] = str(latency_path)

        gpu_profile = self._extract_gpu_profile(run)
        gpu_path = run_dir / "gpu_profile.json"
        with open(gpu_path, "w", encoding="utf-8") as f:
            json.dump(gpu_profile, f, indent=2, default=str)
        artifacts["gpu_profile_json"] = str(gpu_path)

        # report.md
        report_path = run_dir / "report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self._render_markdown(run))
        artifacts["report_md"] = str(report_path)

        logger.info("BenchmarkRun %s artifacts written to %s", run.run_id, run_dir)
        return artifacts

    def _extract_latency_profile(self, run: BenchmarkRun) -> dict:
        profiles = []
        for tr in run.task_results:
            latency = tr.metrics.get("inference_latency", {})
            if latency:
                profiles.append({
                    "task": tr.task,
                    "model_name": tr.model_name,
                    "dataset_name": tr.dataset_name,
                    **latency,
                })
        return {"run_id": run.run_id, "profiles": profiles}

    def _extract_gpu_profile(self, run: BenchmarkRun) -> dict:
        profiles = []
        for tr in run.task_results:
            gpu_profile = tr.metrics.get("gpu_profile", {})
            if gpu_profile:
                profiles.append({
                    "task": tr.task,
                    "model_name": tr.model_name,
                    "dataset_name": tr.dataset_name,
                    **gpu_profile,
                })
        return {"run_id": run.run_id, "profiles": profiles}

    def _render_markdown(self, run: BenchmarkRun) -> str:
        lines = [
            f"# Benchmark Report — {run.run_id}",
            "",
            f"**Timestamp:** {run.timestamp}  ",
            f"**Git commit:** {run.git_commit or 'unknown'}  ",
            f"**Config hash:** {run.config_hash}  ",
            f"**Device:** {run.device}  ",
            "",
        ]

        for tr in run.task_results:
            lines += [
                f"## Task: {tr.task.upper()} — {tr.model_name}",
                "",
            ]
            if tr.skipped:
                lines += [f"> **SKIPPED:** {tr.skip_reason}", ""]
                continue

            latency = tr.metrics.get("inference_latency", {})
            gpu_profile = tr.metrics.get("gpu_profile", {})
            threshold_recommendation = tr.metrics.get("threshold_recommendation", {})
            model_recommendation = tr.metrics.get("model_recommendation", {})
            lines += [
                f"- **Dataset:** {tr.dataset_name}",
                f"- **Dataset size:** {tr.dataset_size}",
                f"- **Class names:** {', '.join(tr.class_names) if tr.class_names else 'n/a'}",
                f"- **Device:** {tr.device}",
                f"- **mAP@0.5:** {tr.metrics.get('map_50')}",
                f"- **mAP@0.5:0.95:** {tr.metrics.get('map_50_95')}",
                f"- **Precision:** {tr.metrics.get('precision')}",
                f"- **Recall:** {tr.metrics.get('recall')}",
                f"- **F1:** {tr.metrics.get('f1')}",
                f"- **FP/image:** {tr.metrics.get('false_positives_per_image')}",
                f"- **FN/image:** {tr.metrics.get('false_negatives_per_image')}",
                f"- **Failure cases:** {tr.failure_cases_count}",
                f"- **p50 latency (ms):** {latency.get('p50_ms')}",
                f"- **p90 latency (ms):** {latency.get('p90_ms')}",
                f"- **p95 latency (ms):** {latency.get('p95_ms')}",
                f"- **p99 latency (ms):** {latency.get('p99_ms')}",
                f"- **Average FPS:** {latency.get('avg_fps')}",
                f"- **GPU memory (MB):** {gpu_profile.get('peak_memory_mb')}",
                "",
                "### Metrics",
                "",
            ]
            for key, val in tr.metrics.items():
                if isinstance(val, dict):
                    lines.append(f"**{key}:**")
                    for k, v in val.items():
                        lines.append(f"  - {k}: {v}")
                elif isinstance(val, list):
                    lines.append(f"**{key}:** (list, {len(val)} items)")
                else:
                    lines.append(f"- **{key}:** {val}")
            lines.append("")

            if tr.warnings:
                lines += ["### Warnings", ""]
                for w in tr.warnings:
                    lines.append(f"- {w}")
                lines.append("")

            if tr.failure_case_summary:
                lines += ["### Failure Case Summary", ""]
                for key, value in tr.failure_case_summary.items():
                    lines.append(f"- **{key}:** {value}")
                lines.append("")

            if threshold_recommendation:
                lines += [
                    "### Threshold Recommendation",
                    "",
                    f"- **Threshold:** {threshold_recommendation.get('threshold')}",
                    f"- **Precision:** {threshold_recommendation.get('precision')}",
                    f"- **Recall:** {threshold_recommendation.get('recall')}",
                    f"- **F1:** {threshold_recommendation.get('f1')}",
                    "",
                ]

            if tr.dataset_improvement_recommendations:
                lines += ["### Dataset Improvement Recommendations", ""]
                for item in tr.dataset_improvement_recommendations:
                    lines.append(f"- {item}")
                lines.append("")

            if model_recommendation:
                lines += [
                    "### Model Recommendation",
                    "",
                    f"- **Recommended model:** {model_recommendation.get('recommended_model')}",
                    f"- **Reason:** {model_recommendation.get('reason')}",
                    f"- **Confidence:** {model_recommendation.get('confidence')}",
                    "",
                ]

        if run.total_warnings:
            lines += ["## Run-level Warnings", ""]
            for w in run.total_warnings:
                lines.append(f"- {w}")

        return "\n".join(lines) + "\n"
