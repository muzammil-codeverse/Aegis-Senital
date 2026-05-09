"""Phase 26 — Integration tests for DetectionBenchmarkRunner with wired predict_fn."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


def _sample(sid, boxes, cls=0):
    return {
        "sample_id": sid,
        "image_path": f"images/{sid}.jpg",
        "annotations": [{"class_id": cls, "bbox_xyxy": box} for box in boxes],
    }


def _make_predict_fn(detections_by_id):
    def predict_fn(image_path):
        sid = Path(image_path).stem
        return detections_by_id.get(sid, [])
    return predict_fn


class TestDetectionBenchmarkRunnerWithRealPredictions:

    def test_runner_produces_metrics_from_real_predictions(self):
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            samples = [_sample("img001", [[0, 0, 100, 100]])]
            predict_fn = _make_predict_fn({
                "img001": [{"bbox": [0, 0, 100, 100], "score": 0.92, "class_id": 0}],
            })
            runner = DetectionBenchmarkRunner(model_name="test_yolo", device="cpu")
            result = runner.run(
                samples=samples,
                predict_fn=predict_fn,
                dataset_name="test_ds",
                class_names=["weapon"],
                run_dir=run_dir,
                save_failure_cases=True,
            )
            assert not result.skipped
            assert result.metrics.get("map_50") is not None
            assert result.metrics.get("precision") is not None
            assert result.metrics.get("recall") is not None

    def test_runner_writes_failure_cases_jsonl(self):
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            samples = [_sample("img001", [[0, 0, 100, 100]])]
            # Predict a FP — no matching GT
            predict_fn = _make_predict_fn({
                "img001": [{"bbox": [500, 500, 600, 600], "score": 0.90, "class_id": 0}],
            })
            runner = DetectionBenchmarkRunner(model_name="test_yolo", device="cpu")
            runner.run(
                samples=samples,
                predict_fn=predict_fn,
                dataset_name="test_ds",
                class_names=["weapon"],
                run_dir=run_dir,
                save_failure_cases=True,
            )
            fc_path = run_dir / "failure_cases.jsonl"
            assert fc_path.exists()
            lines = fc_path.read_text().strip().splitlines()
            assert len(lines) > 0
            fc = json.loads(lines[0])
            assert "failure_type" in fc

    def test_runner_high_confidence_fp_classified_separately(self):
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            samples = [_sample("img001", [])]  # no GT
            predict_fn = _make_predict_fn({
                "img001": [{"bbox": [0, 0, 100, 100], "score": 0.88, "class_id": 0}],
            })
            runner = DetectionBenchmarkRunner(model_name="test_yolo", device="cpu")
            runner.run(
                samples=samples,
                predict_fn=predict_fn,
                dataset_name="ds",
                class_names=["weapon"],
                run_dir=run_dir,
                save_failure_cases=True,
            )
            lines = (run_dir / "failure_cases.jsonl").read_text().strip().splitlines()
            fc = json.loads(lines[0])
            assert fc["failure_type"] == "high_confidence_false_positive"

    def test_runner_failure_case_has_model_name_and_image_path(self):
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            samples = [_sample("img001", [])]
            predict_fn = _make_predict_fn({
                "img001": [{"bbox": [0, 0, 50, 50], "score": 0.30, "class_id": 0}],
            })
            runner = DetectionBenchmarkRunner(model_name="weapon_yolov8", device="cpu")
            runner.run(
                samples=samples,
                predict_fn=predict_fn,
                dataset_name="ds",
                class_names=["weapon"],
                run_dir=run_dir,
                save_failure_cases=True,
            )
            fc = json.loads((run_dir / "failure_cases.jsonl").read_text().strip().splitlines()[0])
            assert fc.get("model_name") == "weapon_yolov8"
            assert "image_path" in fc

    def test_runner_per_class_csv_written(self):
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            samples = [_sample("img001", [[0, 0, 100, 100]])]
            runner = DetectionBenchmarkRunner(model_name="test", device="cpu")
            runner.run(
                samples=samples,
                predict_fn=lambda _: [],
                dataset_name="ds",
                class_names=["weapon"],
                run_dir=run_dir,
                save_failure_cases=False,
            )
            csv_path = run_dir / "per_class_metrics.csv"
            assert csv_path.exists()
            content = csv_path.read_text()
            assert "weapon" in content
            assert "ap_50" in content

    def test_runner_with_map_50_95(self):
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            samples = [_sample("img001", [[0, 0, 100, 100]])]
            predict_fn = _make_predict_fn({
                "img001": [{"bbox": [0, 0, 100, 100], "score": 0.90, "class_id": 0}],
            })
            runner = DetectionBenchmarkRunner(model_name="test", device="cpu")
            result = runner.run(
                samples=samples,
                predict_fn=predict_fn,
                dataset_name="ds",
                class_names=["weapon"],
                run_dir=run_dir,
                save_failure_cases=False,
                compute_map_50_95=True,
            )
            assert result.metrics.get("map_50_95") is not None

    def test_latency_stats_included_when_predictions_made(self):
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            samples = [_sample(f"img{i:03d}", [[0, 0, 50, 50]]) for i in range(5)]
            predict_fn = _make_predict_fn(
                {f"img{i:03d}": [] for i in range(5)}
            )
            runner = DetectionBenchmarkRunner(model_name="test", device="cpu")
            result = runner.run(
                samples=samples,
                predict_fn=predict_fn,
                dataset_name="ds",
                class_names=["weapon"],
                run_dir=run_dir,
                save_failure_cases=False,
            )
            assert "inference_latency" in result.metrics
            lat = result.metrics["inference_latency"]
            assert "p95_ms" in lat
            assert "avg_fps" in lat

    def test_skipped_when_no_samples(self):
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            runner = DetectionBenchmarkRunner(model_name="test", device="cpu")
            result = runner.run(
                samples=[],
                predict_fn=lambda _: [],
                dataset_name="empty_ds",
                class_names=["weapon"],
                run_dir=Path(tmp),
            )
            assert result.skipped

    def test_cpu_fallback_path_works(self):
        """Verify cpu device is accepted without error."""
        from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
        with tempfile.TemporaryDirectory() as tmp:
            runner = DetectionBenchmarkRunner(model_name="test", device="cpu")
            result = runner.run(
                samples=[_sample("img001", [[0, 0, 50, 50]])],
                predict_fn=lambda _: [],
                dataset_name="ds",
                class_names=["weapon"],
                run_dir=Path(tmp),
            )
            assert result.device == "cpu"
