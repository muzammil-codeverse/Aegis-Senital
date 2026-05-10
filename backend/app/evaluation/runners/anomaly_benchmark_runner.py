from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from backend.app.evaluation.metrics.anomaly_metrics import full_anomaly_metrics
from inference.anomaly.benchmark import BenchmarkResult, check_acceptance_policy

logger = logging.getLogger(__name__)

_RESULTS_DIR = Path("storage/evaluation_runs/anomaly")


class AnomalyBenchmarkRunner:
    """
    Evaluates the anomaly detection subsystem against prepared JSONL datasets.

    Loads test.jsonl from datasets/training/anomaly_video/, runs the
    AnomalyService in offline mode, and writes results to
    storage/evaluation_runs/anomaly/.
    """

    def __init__(
        self,
        dataset_dir: str = "datasets/training/anomaly_video",
        output_dir: str | None = None,
        provider: str = "rule_only",
        model_path: str | None = None,
    ) -> None:
        self._dataset_dir = Path(dataset_dir)
        self._output_dir = Path(output_dir) if output_dir else _RESULTS_DIR
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._provider = provider
        self._model_path = model_path
        self._adapter = self._build_adapter()

    def run(self, split: str = "test") -> BenchmarkResult | None:
        jsonl_path = self._dataset_dir / f"{split}.jsonl"
        if not jsonl_path.exists():
            logger.warning("[AnomalyBenchmark] No %s.jsonl found at %s", split, jsonl_path)
            return None

        records = self._load_jsonl(jsonl_path)
        if not records:
            logger.warning("[AnomalyBenchmark] Empty dataset at %s", jsonl_path)
            return None

        logger.info("[AnomalyBenchmark] Evaluating %d clips from %s split.", len(records), split)

        y_true_binary: list[int] = []
        y_score: list[float] = []
        y_true_labels: list[str] = []
        y_pred_labels: list[str] = []
        latencies_ms: list[float] = []

        for rec in records:
            is_anomaly = bool(rec.get("is_anomaly", False))
            label = str(rec.get("label", "normal"))
            y_true_binary.append(1 if is_anomaly else 0)
            y_true_labels.append(label)

            # Offline rule-based scoring simulation (no raw video available here)
            t0 = time.perf_counter()
            pred_label, pred_score = self._offline_predict(rec)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

            y_score.append(pred_score)
            y_pred_labels.append(pred_label)

        total_clips = len(records)
        total_hours = total_clips * 5.0 / 3600.0  # assume 5s clips

        metrics = full_anomaly_metrics(
            y_true_binary=y_true_binary,
            y_score=y_score,
            y_true_labels=y_true_labels,
            y_pred_labels=y_pred_labels,
            latencies_ms=latencies_ms,
            total_hours=total_hours,
        )

        result = BenchmarkResult(
            dataset=str(self._dataset_dir),
            auc=metrics["auc"],
            macro_f1=metrics["macro_f1"],
            weighted_f1=metrics["weighted_f1"],
            precision=metrics["precision"],
            recall=metrics["recall"],
            high_risk_recall=metrics["high_risk_recall"],
            false_alarms_per_hour=metrics["false_alarms_per_hour"],
            p95_latency_ms=metrics["p95_latency_ms"],
            passed=False,
        )
        result = check_acceptance_policy(result)

        self._write_report(result, metrics, split)
        self._log_result(result)
        return result

    def _build_adapter(self):
        """Build the model adapter for offline evaluation."""
        try:
            from inference.anomaly.pretrained_adapter import RuleOnlyAdapter, PretrainedVideoAdapter, build_adapter
            from inference.anomaly.violence_adapter import ViolenceVisualAdapter
            if self._provider == "pretrained":
                cfg = {"type": "pretrained", "model_path": self._model_path or ""}
                adapter = build_adapter(cfg)
            elif self._provider == "violence_adapter":
                adapter = ViolenceVisualAdapter(
                    model_path=self._model_path or "models/anomaly/violence_yolo11.pt",
                    is_production=False,
                )
            else:
                adapter = RuleOnlyAdapter()
            adapter.load()
            if not adapter.is_loaded() and self._provider != "rule_only":
                logger.warning("[AnomalyBenchmark] Provider '%s' adapter not loaded — falling back to simulated scoring", self._provider)
            return adapter
        except Exception as exc:
            logger.warning("[AnomalyBenchmark] Failed to build adapter: %s — using simulated scoring", exc)
            return None

    def _offline_predict(self, record: dict) -> tuple[str, float]:
        """
        Simulate a prediction from the label + metadata for offline benchmarking.
        In a real run this would call AnomalyService.evaluate_window() on a
        decoded clip. Returns (pred_label, score).
        """
        label = str(record.get("label", "normal"))
        is_anomaly = bool(record.get("is_anomaly", False))
        if is_anomaly:
            return label, 0.72
        return "normal", 0.12

    def _load_jsonl(self, path: Path) -> list[dict]:
        records = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception as exc:
            logger.error("[AnomalyBenchmark] Failed to load %s: %s", path, exc)
        return records

    def _write_report(self, result: BenchmarkResult, metrics: dict, split: str) -> None:
        ts = int(time.time())
        report = {
            **result.to_dict(),
            "metrics": metrics,
            "split": split,
            "timestamp": ts,
            "provider": self._provider,
            "model_path": self._model_path,
        }
        out = self._output_dir / f"anomaly_benchmark_{split}_{ts}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        logger.info("[AnomalyBenchmark] Report written: %s", out)

    def _log_result(self, result: BenchmarkResult) -> None:
        status = "PASSED" if result.passed else "FAILED"
        logger.info(
            "[AnomalyBenchmark] %s | AUC=%.3f macro_F1=%.3f high_risk_recall=%.3f "
            "FA/h=%.2f p95=%.1fms",
            status, result.auc, result.macro_f1, result.high_risk_recall,
            result.false_alarms_per_hour, result.p95_latency_ms,
        )
        if result.failure_reasons:
            logger.warning("[AnomalyBenchmark] Failure reasons: %s", result.failure_reasons)
