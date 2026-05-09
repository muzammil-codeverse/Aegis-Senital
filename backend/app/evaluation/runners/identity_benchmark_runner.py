"""Phase 25 — Identity fusion and face/ReID benchmark runner."""
from __future__ import annotations

import logging
from pathlib import Path

from backend.app.evaluation.schemas import BenchmarkTaskResult
from backend.app.evaluation.metrics.face_metrics import compute_face_metrics
from backend.app.evaluation.metrics.reid_metrics import compute_reid_metrics
from backend.app.evaluation.metrics.identity_metrics import compute_identity_metrics

logger = logging.getLogger(__name__)


class FaceBenchmarkRunner:

    def __init__(self, model_name: str = "insightface", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device

    def run(
        self,
        pair_results: list[dict],
        dataset_name: str,
        run_dir: Path,
    ) -> BenchmarkTaskResult:
        warnings = []
        if not pair_results:
            return BenchmarkTaskResult(
                task="face",
                model_name=self.model_name,
                dataset_name=dataset_name,
                skipped=True,
                skip_reason="No face pair results provided",
            )

        metric_result = compute_face_metrics(pair_results)

        self._write_threshold_sweep(metric_result.threshold_sweep, run_dir)

        return BenchmarkTaskResult(
            task="face",
            model_name=self.model_name,
            device=self.device,
            dataset_name=dataset_name,
            metrics=metric_result.to_dict(),
            warnings=warnings + metric_result.warnings,
        )

    def _write_threshold_sweep(self, sweep: list[dict], run_dir: Path) -> None:
        import csv
        out = run_dir / "threshold_sweep.csv"
        if not sweep:
            return
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sweep[0].keys())
            writer.writeheader()
            writer.writerows(sweep)


class ReIDBenchmarkRunner:

    def __init__(self, model_name: str = "osnet", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device

    def run(
        self,
        query_embeddings: list[dict],
        gallery_embeddings: list[dict],
        dataset_name: str,
        run_dir: Path,
    ) -> BenchmarkTaskResult:
        if not query_embeddings:
            return BenchmarkTaskResult(
                task="reid",
                model_name=self.model_name,
                dataset_name=dataset_name,
                skipped=True,
                skip_reason="No ReID query embeddings",
            )

        metric_result = compute_reid_metrics(query_embeddings, gallery_embeddings)

        return BenchmarkTaskResult(
            task="reid",
            model_name=self.model_name,
            device=self.device,
            dataset_name=dataset_name,
            metrics=metric_result.to_dict(),
            warnings=metric_result.warnings,
        )


class IdentityFusionBenchmarkRunner:

    def run(
        self,
        scenario_results: dict[str, dict],
        merge_events: list[dict] | None,
        dataset_name: str,
    ) -> BenchmarkTaskResult:
        metric_result = compute_identity_metrics(scenario_results, merge_events)
        return BenchmarkTaskResult(
            task="identity_fusion",
            model_name="identity_fusion_engine",
            dataset_name=dataset_name,
            metrics=metric_result.to_dict(),
            warnings=metric_result.warnings,
        )
