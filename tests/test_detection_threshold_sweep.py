"""Phase 26 — Tests for confidence threshold sweep."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest


def _sample(sid, box, cls=0):
    return {"sample_id": sid, "image_path": f"img/{sid}.jpg",
            "annotations": [{"class_id": cls, "bbox_xyxy": box}]}


def _pred(sid, box, score, cls=0):
    return [{"bbox": box, "score": score, "class_id": cls}]


class TestThresholdSweep:

    def test_sweep_returns_rows_for_each_threshold(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_threshold_sweep
        samples = [_sample("s1", [0, 0, 100, 100])]
        preds = {"s1": _pred("s1", [0, 0, 100, 100], score=0.5)}
        thresholds = [0.1, 0.3, 0.5, 0.7]
        rows = compute_threshold_sweep(samples, preds, class_names=["weapon"], thresholds=thresholds)
        assert len(rows) > 0
        # "all" + "weapon" per threshold = 2 * 4 = 8 rows
        assert len(rows) == 2 * len(thresholds)

    def test_high_threshold_filters_low_score_predictions(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_threshold_sweep
        samples = [_sample("s1", [0, 0, 100, 100])]
        # Prediction score = 0.3 — filtered out at threshold 0.5
        preds = {"s1": _pred("s1", [0, 0, 100, 100], score=0.3)}
        rows = compute_threshold_sweep(samples, preds, class_names=["weapon"], thresholds=[0.5])
        all_row = next(r for r in rows if r["class"] == "all")
        # At threshold 0.5, the 0.3-score pred is excluded → 0 detections → recall = 0
        assert all_row["recall"] == 0.0

    def test_low_threshold_includes_all_predictions(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_threshold_sweep
        samples = [_sample("s1", [0, 0, 100, 100])]
        preds = {"s1": _pred("s1", [0, 0, 100, 100], score=0.3)}
        rows = compute_threshold_sweep(samples, preds, class_names=["weapon"], thresholds=[0.1])
        all_row = next(r for r in rows if r["class"] == "all")
        # At threshold 0.1, the 0.3-score pred is included → recall > 0
        assert all_row["recall"] > 0.0

    def test_row_schema(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_threshold_sweep
        samples = [_sample("s1", [0, 0, 100, 100])]
        preds = {"s1": _pred("s1", [0, 0, 100, 100], score=0.8)}
        rows = compute_threshold_sweep(samples, preds, class_names=["weapon"], thresholds=[0.5],
                                       model_name="baseline")
        assert rows
        row = rows[0]
        assert "model_name" in row
        assert "class" in row
        assert "threshold" in row
        assert "precision" in row
        assert "recall" in row
        assert "f1" in row
        assert "fp_per_image" in row
        assert "fn_per_image" in row
        assert row["model_name"] == "baseline"

    def test_default_thresholds_used(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_threshold_sweep
        samples = [_sample("s1", [0, 0, 100, 100])]
        rows = compute_threshold_sweep(samples, {}, class_names=["weapon"])
        thresholds_seen = {r["threshold"] for r in rows}
        # Default thresholds include 0.10 and 0.70
        assert 0.10 in thresholds_seen
        assert 0.70 in thresholds_seen

    def test_sweep_csv_written_by_runner(self):
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            samples = [{"sample_id": "s1", "image_path": "img/s1.jpg",
                        "annotations": [{"class_id": 0, "bbox_xyxy": [0, 0, 100, 100]}]}]
            runner = DetectionBenchmarkRunner(model_name="test", device="cpu")
            runner.run(
                samples=samples,
                predict_fn=lambda _: [],
                dataset_name="test_ds",
                class_names=["weapon"],
                run_dir=run_dir,
                save_failure_cases=False,
                threshold_sweep_config={"enabled": True, "thresholds": [0.3, 0.5]},
            )
            csv_path = run_dir / "threshold_sweep.csv"
            assert csv_path.exists()
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) > 0
            assert "threshold" in rows[0]
