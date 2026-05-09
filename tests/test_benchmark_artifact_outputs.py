from __future__ import annotations

from pathlib import Path


def _sample(sample_id: str, box: list[int]) -> dict:
    return {
        "sample_id": sample_id,
        "image_path": f"images/{sample_id}.jpg",
        "annotations": [{"class_id": 0, "bbox_xyxy": box, "class_name": "weapon"}],
    }


def test_detection_benchmark_writes_expected_artifacts(tmp_path: Path):
    from backend.app.evaluation.benchmark_config import save_config_snapshot
    from backend.app.evaluation.reports.report_writer import ReportWriter
    from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
    from backend.app.evaluation.schemas import BenchmarkRun

    run_dir = tmp_path / "run_001"
    run_dir.mkdir(parents=True, exist_ok=True)
    save_config_snapshot(run_dir, {"evaluation": {"device": "cpu"}})

    runner = DetectionBenchmarkRunner(model_name="weapon_yolov8_baseline", model_path="models/weapon/model.pt", device="cpu")
    result = runner.run(
        samples=[_sample("img001", [0, 0, 100, 100])],
        predict_fn=lambda _: [{"bbox": [0, 0, 100, 100], "score": 0.95, "class_id": 0}],
        dataset_name="weapon_eval",
        class_names=["weapon"],
        run_dir=run_dir,
        save_failure_cases=True,
        compute_map_50_95=True,
        threshold_sweep_config={"enabled": True, "thresholds": [0.25, 0.5]},
    )
    result.metrics["gpu_profile"] = {
        "gpu_available": False,
        "peak_memory_mb": None,
        "profiling_degraded": True,
        "degradation_reason": "CPU test fixture",
    }
    result.metrics["model_recommendation"] = {
        "recommended_model": "weapon_yolov8_baseline",
        "reason": "fixture recommendation",
        "confidence": "medium",
    }

    run = BenchmarkRun(run_id="run_001", git_commit="abc123", config_hash="deadbeef", device="cpu")
    run.task_results.append(result)
    ReportWriter().write(run, run_dir)

    expected = [
        "config_snapshot.yaml",
        "metrics.json",
        "report.md",
        "per_class_metrics.csv",
        "threshold_sweep.csv",
        "failure_cases.jsonl",
        "latency_profile.json",
        "gpu_profile.json",
    ]
    for name in expected:
        assert (run_dir / name).exists(), f"missing artifact: {name}"
