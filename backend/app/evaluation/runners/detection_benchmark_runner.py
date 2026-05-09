"""Phase 25 — Detection benchmark runner."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from backend.app.evaluation.schemas import BenchmarkTaskResult, FailureCase
from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics

logger = logging.getLogger(__name__)


class DetectionBenchmarkRunner:
    """
    Runs detection evaluation on a YOLO/COCO dataset.
    Writes per-class metrics CSV, confusion matrix CSV, and failure cases JSONL.
    """

    def __init__(
        self,
        model_name: str,
        model_path: str,
        device: str = "cpu",
        model_version: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_path = model_path
        self.device = device
        self.model_version = model_version

    def run(
        self,
        samples: list[dict],
        predict_fn,
        dataset_name: str,
        class_names: list[str],
        run_dir: Path,
        dataset_version: str | None = None,
        save_failure_cases: bool = True,
    ) -> BenchmarkTaskResult:
        """
        Run detection evaluation.

        samples: output of CocoYoloLoader.load_yolo_annotations()
        predict_fn: callable(image_path) → [{"bbox": [x1,y1,x2,y2], "score": float, "class_id": int}]
        """
        warnings = []
        if not samples:
            warnings.append(f"No samples in dataset '{dataset_name}'")
            return BenchmarkTaskResult(
                task="detection",
                model_name=self.model_name,
                dataset_name=dataset_name,
                device=self.device,
                skipped=True,
                skip_reason="No samples",
                warnings=warnings,
            )

        predictions_by_sample: dict[str, list[dict]] = {}
        failure_cases: list[FailureCase] = []

        for sample in samples:
            sample_id = sample.get("sample_id", "")
            image_path = sample.get("image_path")
            if not image_path:
                warnings.append(f"Missing image path for sample {sample_id}")
                continue

            try:
                preds = predict_fn(image_path)
                predictions_by_sample[sample_id] = preds
            except Exception as exc:
                logger.warning("Prediction failed for %s: %s", image_path, exc)
                warnings.append(f"Prediction failed for {sample_id}: {exc}")
                predictions_by_sample[sample_id] = []

        metric_result = compute_detection_metrics(
            samples=samples,
            predictions_by_sample=predictions_by_sample,
            class_names=class_names,
        )

        if save_failure_cases:
            failure_cases = self._collect_failures(
                samples, predictions_by_sample, class_names
            )
            self._write_failure_cases(failure_cases, run_dir)

        # Write per-class metrics CSV
        self._write_per_class_csv(metric_result.per_class_ap, run_dir)

        return BenchmarkTaskResult(
            task="detection",
            model_name=self.model_name,
            model_path=self.model_path,
            model_version=self.model_version,
            device=self.device,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            metrics=metric_result.to_dict(),
            failure_cases_count=len(failure_cases),
            warnings=warnings + metric_result.warnings,
        )

    def _collect_failures(
        self,
        samples: list[dict],
        predictions_by_sample: dict[str, list[dict]],
        class_names: list[str],
    ) -> list[FailureCase]:
        failures = []
        for sample in samples:
            sample_id = sample.get("sample_id", "")
            gt_anns = sample.get("annotations", [])
            preds = predictions_by_sample.get(sample_id, [])

            gt_matched = [False] * len(gt_anns)
            for pred in preds:
                matched = False
                for i, gt in enumerate(gt_anns):
                    if gt_matched[i]:
                        continue
                    if gt.get("class_id") != pred.get("class_id"):
                        continue
                    from backend.app.evaluation.metrics.detection_metrics import compute_iou
                    bbox_gt = gt.get("bbox_xyxy") or gt.get("bbox_cxcywh_norm", [])
                    bbox_pred = pred.get("bbox", [])
                    if len(bbox_gt) == 4 and len(bbox_pred) == 4:
                        iou = compute_iou(bbox_pred, bbox_gt)
                        if iou >= 0.5:
                            gt_matched[i] = True
                            matched = True
                            break
                if not matched:
                    failures.append(FailureCase(
                        task="detection",
                        sample_id=sample_id,
                        frame_id=0,
                        failure_type="false_positive",
                        expected={},
                        actual={"class_id": pred.get("class_id"), "score": pred.get("score", 0.0)},
                        confidence=pred.get("score", 0.0),
                    ))

            for i, (gt, matched) in enumerate(zip(gt_anns, gt_matched)):
                if not matched:
                    failures.append(FailureCase(
                        task="detection",
                        sample_id=sample_id,
                        frame_id=0,
                        failure_type="false_negative",
                        expected={"class_id": gt.get("class_id"), "class_name": gt.get("class_name")},
                        actual={},
                        confidence=0.0,
                    ))

        return failures

    def _write_failure_cases(self, cases: list[FailureCase], run_dir: Path) -> None:
        out_path = run_dir / "failure_cases.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for fc in cases:
                f.write(json.dumps(fc.to_dict()) + "\n")
        logger.info("Wrote %d failure cases to %s", len(cases), out_path)

    def _write_per_class_csv(self, per_class_ap: dict[str, float], run_dir: Path) -> None:
        out_path = run_dir / "per_class_metrics.csv"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("class_name,ap\n")
            for cls, ap in per_class_ap.items():
                f.write(f"{cls},{ap}\n")
