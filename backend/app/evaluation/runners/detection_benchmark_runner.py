"""Phase 25/26 — Detection benchmark runner with real inference wiring."""
from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from backend.app.evaluation.schemas import BenchmarkTaskResult, FailureCase
from backend.app.evaluation.metrics.detection_metrics import (
    compute_detection_metrics,
    compute_threshold_sweep,
    compute_iou,
)

logger = logging.getLogger(__name__)

_HIGH_CONF_FP_THRESHOLD = 0.70
_LOW_CONF_TP_THRESHOLD = 0.30
_LOW_IOU_MATCH_THRESHOLD = 0.60
_FAILURE_TYPES = (
    "false_positive",
    "false_negative",
    "high_confidence_false_positive",
    "low_iou_match",
    "class_confusion",
    "low_confidence_true_positive",
)


class DetectionBenchmarkRunner:
    """
    Runs detection evaluation on a YOLO/COCO dataset.

    Supports:
    - Real inference via DetectionModelAdapter.predict() or a callable predict_fn
    - mAP@0.5 (always) and mAP@0.5:0.95 (when compute_map_50_95=True)
    - Confidence threshold sweep (when enabled in config)
    - Extended failure-case mining (FP, FN, high-conf FP, low-IoU match, class confusion)
    - Per-class metrics CSV
    """

    def __init__(
        self,
        model_name: str,
        model_path: str = "",
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
        predict_fn: Callable[[str], list[dict]],
        dataset_name: str,
        class_names: list[str],
        run_dir: Path,
        dataset_version: str | None = None,
        save_failure_cases: bool = True,
        compute_map_50_95: bool = False,
        threshold_sweep_config: dict | None = None,
        failure_case_export_config: dict | None = None,
    ) -> BenchmarkTaskResult:
        """
        Run detection evaluation.

        predict_fn: callable(image_path) → [{"bbox": [x1,y1,x2,y2], "score": float, "class_id": int}]
        threshold_sweep_config: {"enabled": bool, "thresholds": [...]}
        failure_case_export_config: {"copy_images": bool, "crop_false_positives": bool,
                                     "max_cases_per_type": int}
        """
        warnings: list[str] = []
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
        latency_samples: list[float] = []

        for sample in samples:
            sample_id = sample.get("sample_id", "")
            image_path = sample.get("image_path")
            if not image_path:
                warnings.append(f"Missing image path for sample {sample_id}")
                predictions_by_sample[sample_id] = []
                continue

            t0 = time.perf_counter()
            try:
                preds = predict_fn(image_path)
                latency_ms = (time.perf_counter() - t0) * 1000
                latency_samples.append(latency_ms)
                predictions_by_sample[sample_id] = preds or []
            except Exception as exc:
                logger.warning("Prediction failed for %s: %s", image_path, exc)
                warnings.append(f"Prediction failed for {sample_id}: {exc}")
                predictions_by_sample[sample_id] = []

        metric_result = compute_detection_metrics(
            samples=samples,
            predictions_by_sample=predictions_by_sample,
            class_names=class_names,
            compute_map_50_95=compute_map_50_95,
        )

        # Failure case mining
        failure_cases: list[FailureCase] = []
        if save_failure_cases:
            max_per_type = (failure_case_export_config or {}).get("max_cases_per_type", 100)
            failure_cases = self._collect_failures(
                samples, predictions_by_sample, class_names, max_per_type=max_per_type,
            )
            self._write_failure_cases(failure_cases, run_dir)
        failure_case_summary = self._summarize_failures(failure_cases)

        # Per-class metrics CSV
        self._write_per_class_csv(metric_result, run_dir)

        # Latency stats
        latency_stats: dict = {}
        if latency_samples:
            latency_stats = _compute_latency_stats(latency_samples)
            metric_result.warnings  # not mutating

        # Threshold sweep
        threshold_recommendation: dict = {}
        if threshold_sweep_config and threshold_sweep_config.get("enabled"):
            thresholds = threshold_sweep_config.get("thresholds")
            sweep_rows = compute_threshold_sweep(
                samples=samples,
                predictions_by_sample=predictions_by_sample,
                class_names=class_names,
                model_name=self.model_name,
                thresholds=thresholds,
            )
            self._write_threshold_sweep_csv(sweep_rows, run_dir)
            threshold_recommendation = self._recommend_threshold(sweep_rows)

        metrics = metric_result.to_dict()
        if latency_stats:
            metrics["inference_latency"] = latency_stats
        if threshold_recommendation:
            metrics["threshold_recommendation"] = threshold_recommendation

        return BenchmarkTaskResult(
            task="detection",
            model_name=self.model_name,
            model_path=self.model_path,
            model_version=self.model_version,
            device=self.device,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            dataset_size=len(samples),
            class_names=list(class_names),
            metrics=metrics,
            failure_cases_count=len(failure_cases),
            failure_case_summary=failure_case_summary,
            dataset_improvement_recommendations=self._dataset_improvement_recommendations(dataset_name),
            real_run=True,
            warnings=warnings + metric_result.warnings,
        )

    # ── failure case mining ───────────────────────────────────────────────────

    def _collect_failures(
        self,
        samples: list[dict],
        predictions_by_sample: dict[str, list[dict]],
        class_names: list[str],
        max_per_type: int = 100,
    ) -> list[FailureCase]:
        counters: dict[str, int] = {}
        failures: list[FailureCase] = []

        for sample in samples:
            sample_id = sample.get("sample_id", "")
            image_path = sample.get("image_path", "")
            gt_anns = sample.get("annotations", [])
            preds = sorted(
                predictions_by_sample.get(sample_id, []),
                key=lambda p: p.get("score", 0.0),
                reverse=True,
            )

            gt_matched = [False] * len(gt_anns)
            for pred in preds:
                pred_box = pred.get("bbox", [])
                pred_cls = pred.get("class_id", 0)
                pred_score = pred.get("score", 0.0)
                best_iou = 0.0
                best_gt_idx = -1
                best_gt_cls = -1

                for i, gt in enumerate(gt_anns):
                    if gt_matched[i]:
                        continue
                    gt_box = gt.get("bbox") or gt.get("bbox_xyxy") or []
                    if len(gt_box) < 4 or len(pred_box) < 4:
                        continue
                    iou = compute_iou(pred_box, gt_box)
                    if iou > best_iou:
                        best_iou = iou
                        best_gt_idx = i
                        best_gt_cls = gt.get("class_id", -1)

                matched = best_iou >= 0.5 and best_gt_idx >= 0
                if matched:
                    gt_matched[best_gt_idx] = True
                    if best_iou < _LOW_IOU_MATCH_THRESHOLD:
                        failures.extend(self._add_case(
                            counters, "low_iou_match", max_per_type,
                            FailureCase(
                                task="detection",
                                model_name=self.model_name,
                                sample_id=sample_id,
                                image_path=image_path,
                                frame_id=0,
                                failure_type="low_iou_match",
                                expected={"class_id": best_gt_cls, "iou": round(best_iou, 4)},
                                actual={"bbox": pred_box, "score": pred_score, "class_id": pred_cls},
                                confidence=pred_score,
                                notes=f"IoU={best_iou:.3f} below {_LOW_IOU_MATCH_THRESHOLD}",
                            )
                        ))
                    if pred_score < _LOW_CONF_TP_THRESHOLD:
                        failures.extend(self._add_case(
                            counters, "low_confidence_true_positive", max_per_type,
                            FailureCase(
                                task="detection",
                                model_name=self.model_name,
                                sample_id=sample_id,
                                image_path=image_path,
                                frame_id=0,
                                failure_type="low_confidence_true_positive",
                                expected={},
                                actual={"bbox": pred_box, "score": pred_score, "class_id": pred_cls},
                                confidence=pred_score,
                                notes=f"TP with low confidence {pred_score:.3f}",
                            )
                        ))
                else:
                    # False positive
                    ft = "false_positive"
                    if pred_score >= _HIGH_CONF_FP_THRESHOLD:
                        ft = "high_confidence_false_positive"
                    failures.extend(self._add_case(
                        counters, ft, max_per_type,
                        FailureCase(
                            task="detection",
                            model_name=self.model_name,
                            sample_id=sample_id,
                            image_path=image_path,
                            frame_id=0,
                            failure_type=ft,
                            expected={},
                            actual={"bbox": pred_box, "score": pred_score, "class_id": pred_cls,
                                    "label": class_names[pred_cls] if pred_cls < len(class_names) else str(pred_cls)},
                            confidence=pred_score,
                            notes="Candidate for hard-negative dataset review" if ft == "high_confidence_false_positive" else "",
                        )
                    ))
                    # Class confusion: check if there's a GT box of a different class with decent IoU
                    for gt in gt_anns:
                        gt_box = gt.get("bbox") or gt.get("bbox_xyxy") or []
                        if len(gt_box) < 4 or len(pred_box) < 4:
                            continue
                        if gt.get("class_id") == pred_cls:
                            continue
                        iou = compute_iou(pred_box, gt_box)
                        if iou >= 0.5:
                            failures.extend(self._add_case(
                                counters, "class_confusion", max_per_type,
                                FailureCase(
                                    task="detection",
                                    model_name=self.model_name,
                                    sample_id=sample_id,
                                    image_path=image_path,
                                    frame_id=0,
                                    failure_type="class_confusion",
                                    expected={"class_id": gt.get("class_id")},
                                    actual={"class_id": pred_cls, "score": pred_score},
                                    confidence=pred_score,
                                    notes=f"Predicted class {pred_cls}, GT class {gt.get('class_id')}",
                                )
                            ))
                            break

            # False negatives
            for i, (gt, matched) in enumerate(zip(gt_anns, gt_matched)):
                if not matched:
                    failures.extend(self._add_case(
                        counters, "false_negative", max_per_type,
                        FailureCase(
                            task="detection",
                            model_name=self.model_name,
                            sample_id=sample_id,
                            image_path=image_path,
                            frame_id=0,
                            failure_type="false_negative",
                            expected={"class_id": gt.get("class_id"), "class_name": gt.get("class_name")},
                            actual={},
                            confidence=0.0,
                        )
                    ))

        return failures

    @staticmethod
    def _add_case(counters: dict, failure_type: str, max_per_type: int, case: FailureCase) -> list[FailureCase]:
        if counters.get(failure_type, 0) < max_per_type:
            counters[failure_type] = counters.get(failure_type, 0) + 1
            return [case]
        return []

    # ── artifact writers ──────────────────────────────────────────────────────

    def _write_failure_cases(self, cases: list[FailureCase], run_dir: Path) -> None:
        out_path = run_dir / "failure_cases.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for fc in cases:
                f.write(json.dumps(fc.to_dict()) + "\n")
        logger.info("Wrote %d failure cases to %s", len(cases), out_path)

    def _write_per_class_csv(self, metric_result, run_dir: Path) -> None:
        out_path = run_dir / "per_class_metrics.csv"
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["class_name", "ap_50", "ap_50_95", "precision", "recall", "f1",
                            "num_gt", "num_detections"],
            )
            writer.writeheader()
            for cls_name, metrics in metric_result.per_class_metrics.items():
                writer.writerow({
                    "class_name": cls_name,
                    "ap_50": metrics.get("ap_50", ""),
                    "ap_50_95": metrics.get("ap_50_95", ""),
                    "precision": metrics.get("precision", ""),
                    "recall": metrics.get("recall", ""),
                    "f1": metrics.get("f1", ""),
                    "num_gt": metrics.get("num_gt", ""),
                    "num_detections": metrics.get("num_detections", ""),
                })
        logger.info("Wrote per-class metrics CSV to %s", out_path)

    def _write_threshold_sweep_csv(self, rows: list[dict], run_dir: Path) -> None:
        if not rows:
            return
        out_path = run_dir / "threshold_sweep.csv"
        fieldnames = ["model_name", "class", "threshold", "precision", "recall", "f1",
                      "fp_per_image", "fn_per_image", "map_50", "map_50_95"]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info("Wrote threshold sweep CSV to %s", out_path)

    def _summarize_failures(self, cases: list[FailureCase]) -> dict[str, int]:
        summary = {name: 0 for name in _FAILURE_TYPES}
        for case in cases:
            if case.failure_type in summary:
                summary[case.failure_type] += 1
        return summary

    def _recommend_threshold(self, rows: list[dict]) -> dict:
        all_rows = [row for row in rows if row.get("class") == "all"]
        if not all_rows:
            return {}
        best = max(
            all_rows,
            key=lambda row: (
                float(row.get("f1", 0.0) or 0.0),
                float(row.get("recall", 0.0) or 0.0),
                -float(row.get("fp_per_image", 0.0) or 0.0),
            ),
        )
        return {
            "threshold": best.get("threshold"),
            "precision": best.get("precision"),
            "recall": best.get("recall"),
            "f1": best.get("f1"),
            "fp_per_image": best.get("fp_per_image"),
            "fn_per_image": best.get("fn_per_image"),
        }

    def _dataset_improvement_recommendations(self, dataset_name: str) -> list[str]:
        lowered = dataset_name.lower()
        if "weapon" in lowered:
            return [
                "add hard negatives for weapon-like objects",
                "add low-light samples",
                "add occluded weapon samples",
                "add CCTV-angle samples",
                "add small-object distant samples",
            ]
        if "phone" in lowered:
            return [
                "add reflective phone-like objects",
                "add CCTV-angle samples",
                "add small-object distant samples",
                "add low-light samples",
            ]
        return [
            "add low-light samples",
            "add CCTV-angle samples",
            "add small-object distant samples",
        ]


# ── helpers ───────────────────────────────────────────────────────────────────

def _compute_latency_stats(latency_samples: list[float]) -> dict:
    if not latency_samples:
        return {}
    s = sorted(latency_samples)
    n = len(s)

    def _pct(p: float) -> float:
        idx = min(int(p * n / 100), n - 1)
        return round(s[idx], 3)

    return {
        "count": n,
        "mean_ms": round(sum(s) / n, 3),
        "p50_ms": _pct(50),
        "p90_ms": _pct(90),
        "p95_ms": _pct(95),
        "p99_ms": _pct(99),
        "min_ms": round(s[0], 3),
        "max_ms": round(s[-1], 3),
        "avg_fps": round(1000.0 / (sum(s) / n), 1) if sum(s) > 0 else 0.0,
    }
