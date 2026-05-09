"""Phase 25 — Tracking benchmark runner (MOTChallenge-style)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.app.evaluation.schemas import BenchmarkTaskResult, FailureCase
from backend.app.evaluation.metrics.tracking_metrics import compute_tracking_metrics

logger = logging.getLogger(__name__)


class TrackingBenchmarkRunner:

    def __init__(self, model_name: str = "stream_tracker", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device

    def run(
        self,
        gt_by_frame: dict[int, list[dict]],
        pred_by_frame: dict[int, list[dict]],
        dataset_name: str,
        run_dir: Path,
        save_failure_cases: bool = True,
    ) -> BenchmarkTaskResult:
        warnings = []
        if not gt_by_frame:
            return BenchmarkTaskResult(
                task="tracking",
                model_name=self.model_name,
                dataset_name=dataset_name,
                skipped=True,
                skip_reason="No ground-truth tracking data",
            )

        metric_result = compute_tracking_metrics(gt_by_frame, pred_by_frame)

        failure_cases = []
        if save_failure_cases:
            failure_cases = self._collect_id_switches(gt_by_frame, pred_by_frame)
            self._write_failure_cases(failure_cases, run_dir)

        return BenchmarkTaskResult(
            task="tracking",
            model_name=self.model_name,
            device=self.device,
            dataset_name=dataset_name,
            metrics=metric_result.to_dict(),
            failure_cases_count=len(failure_cases),
            warnings=warnings + metric_result.warnings,
        )

    def _collect_id_switches(
        self,
        gt_by_frame: dict[int, list[dict]],
        pred_by_frame: dict[int, list[dict]],
    ) -> list[FailureCase]:
        failures = []
        prev_gt_to_pred: dict[int, int] = {}
        for frame_id in sorted(gt_by_frame.keys()):
            gt_list = gt_by_frame.get(frame_id, [])
            pred_list = pred_by_frame.get(frame_id, [])
            for gt in gt_list:
                gt_tid = gt["track_id"]
                for pred in pred_list:
                    prev = prev_gt_to_pred.get(gt_tid)
                    if prev is not None and prev != pred["track_id"]:
                        failures.append(FailureCase(
                            task="tracking",
                            sample_id=str(frame_id),
                            frame_id=frame_id,
                            failure_type="id_switch",
                            expected={"track_id": prev},
                            actual={"track_id": pred["track_id"]},
                            confidence=pred.get("conf", 0.0),
                        ))
                    prev_gt_to_pred[gt_tid] = pred["track_id"]
        return failures

    def _write_failure_cases(self, cases: list[FailureCase], run_dir: Path) -> None:
        out_path = run_dir / "failure_cases.jsonl"
        mode = "a" if out_path.exists() else "w"
        with open(out_path, mode, encoding="utf-8") as f:
            for fc in cases:
                f.write(json.dumps(fc.to_dict()) + "\n")
