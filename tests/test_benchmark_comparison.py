"""
Phase 25 — Tests for benchmark comparison logic and regression detection.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


def _write_run(run_dir: Path, metrics: dict, run_id: str = "test_run") -> None:
    from backend.app.evaluation.schemas import BenchmarkRun, BenchmarkTaskResult
    run = BenchmarkRun(run_id=run_id, device="cpu")
    for task, task_metrics in metrics.items():
        run.task_results.append(BenchmarkTaskResult(
            task=task,
            model_name=f"{task}_model",
            dataset_name=f"{task}_eval",
            metrics=task_metrics,
        ))
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "metrics.json", "w") as f:
        json.dump(run.to_dict(), f, indent=2, default=str)


class TestBenchmarkComparator:

    def test_improved_metric_detected(self):
        from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
        with tempfile.TemporaryDirectory() as tmp:
            baseline_dir = Path(tmp) / "baseline"
            candidate_dir = Path(tmp) / "candidate"
            _write_run(baseline_dir, {"detection": {"map_50": 0.70}}, "baseline")
            _write_run(candidate_dir, {"detection": {"map_50": 0.75}}, "candidate")

            comparator = BenchmarkComparator()
            comparison = comparator.compare(baseline_dir, candidate_dir)

            map_delta = next((d for d in comparison.deltas if "map_50" in d.metric), None)
            assert map_delta is not None
            assert map_delta.status == "improved"
            assert map_delta.absolute_change > 0

    def test_regressed_metric_detected(self):
        from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
        with tempfile.TemporaryDirectory() as tmp:
            baseline_dir = Path(tmp) / "baseline"
            candidate_dir = Path(tmp) / "candidate"
            _write_run(baseline_dir, {"detection": {"map_50": 0.75}}, "baseline")
            _write_run(candidate_dir, {"detection": {"map_50": 0.65}}, "candidate")

            comparator = BenchmarkComparator()
            comparison = comparator.compare(baseline_dir, candidate_dir)

            map_delta = next((d for d in comparison.deltas if "map_50" in d.metric), None)
            assert map_delta is not None
            assert map_delta.status == "regressed"

    def test_regression_policy_fail(self):
        from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
        policy = {"detection_map_drop_warn": 0.02, "detection_map_drop_fail": 0.05}
        with tempfile.TemporaryDirectory() as tmp:
            baseline_dir = Path(tmp) / "baseline"
            candidate_dir = Path(tmp) / "candidate"
            _write_run(baseline_dir, {"detection": {"map_50": 0.80}}, "baseline")
            _write_run(candidate_dir, {"detection": {"map_50": 0.70}}, "candidate")  # -0.10 > fail threshold

            comparator = BenchmarkComparator(regression_policy=policy)
            comparison = comparator.compare(baseline_dir, candidate_dir)
            assert comparison.overall_status == "fail"

    def test_regression_policy_warn(self):
        from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
        policy = {"detection_map_drop_warn": 0.02, "detection_map_drop_fail": 0.05}
        with tempfile.TemporaryDirectory() as tmp:
            baseline_dir = Path(tmp) / "baseline"
            candidate_dir = Path(tmp) / "candidate"
            _write_run(baseline_dir, {"detection": {"map_50": 0.72}}, "baseline")
            _write_run(candidate_dir, {"detection": {"map_50": 0.69}}, "candidate")  # -0.03 in warn zone

            comparator = BenchmarkComparator(regression_policy=policy)
            comparison = comparator.compare(baseline_dir, candidate_dir)
            assert comparison.overall_status in ("warn", "fail")

    def test_no_regression_pass(self):
        from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
        with tempfile.TemporaryDirectory() as tmp:
            baseline_dir = Path(tmp) / "baseline"
            candidate_dir = Path(tmp) / "candidate"
            _write_run(baseline_dir, {"detection": {"map_50": 0.72}}, "baseline")
            _write_run(candidate_dir, {"detection": {"map_50": 0.72}}, "candidate")  # identical

            comparator = BenchmarkComparator()
            comparison = comparator.compare(baseline_dir, candidate_dir)
            assert comparison.overall_status == "pass"

    def test_comparison_report_written(self):
        from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
        with tempfile.TemporaryDirectory() as tmp:
            baseline_dir = Path(tmp) / "baseline"
            candidate_dir = Path(tmp) / "candidate"
            _write_run(baseline_dir, {"detection": {"map_50": 0.72}}, "baseline")
            _write_run(candidate_dir, {"detection": {"map_50": 0.75}}, "candidate")

            comparator = BenchmarkComparator()
            comparison = comparator.compare(baseline_dir, candidate_dir)
            out = Path(tmp) / "comparison.md"
            comparator.write_report(comparison, out)
            assert out.exists()
            content = out.read_text()
            assert "Baseline" in content
            assert "Candidate" in content

    def test_missing_metrics_json_raises(self):
        from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
        with tempfile.TemporaryDirectory() as tmp:
            comparator = BenchmarkComparator()
            with pytest.raises(FileNotFoundError):
                comparator.compare(Path(tmp) / "nonexistent_baseline", Path(tmp) / "nonexistent_candidate")

    def test_skipped_tasks_excluded_from_deltas(self):
        from backend.app.evaluation.schemas import BenchmarkRun, BenchmarkTaskResult
        from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("baseline", "candidate"):
                d = Path(tmp) / name
                d.mkdir()
                run = BenchmarkRun(run_id=name, device="cpu")
                run.task_results.append(BenchmarkTaskResult(
                    task="tracking",
                    model_name="tracker",
                    dataset_name="mot",
                    skipped=True,
                    skip_reason="No data",
                ))
                run.task_results.append(BenchmarkTaskResult(
                    task="detection",
                    model_name="yolo",
                    dataset_name="weapon_eval",
                    metrics={"map_50": 0.70},
                ))
                with open(d / "metrics.json", "w") as f:
                    json.dump(run.to_dict(), f, default=str)

            comparator = BenchmarkComparator()
            comparison = comparator.compare(Path(tmp) / "baseline", Path(tmp) / "candidate")
            # Skipped tasks produce no deltas
            tracking_deltas = [d for d in comparison.deltas if d.metric.startswith("tracking")]
            assert len(tracking_deltas) == 0


class TestFailureCaseExport:

    def test_failure_case_schema(self):
        from backend.app.evaluation.schemas import FailureCase
        fc = FailureCase(
            task="detection",
            sample_id="img_001",
            frame_id=42,
            camera_id="cam_01",
            failure_type="false_positive",
            expected={},
            actual={"class_id": 0, "score": 0.75},
            confidence=0.75,
            notes="high confidence FP on background",
        )
        d = fc.to_dict()
        assert d["task"] == "detection"
        assert d["failure_type"] == "false_positive"
        json.dumps(d)  # must serialize

    def test_failure_case_written_as_jsonl(self):
        from backend.app.evaluation.schemas import FailureCase
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "failure_cases.jsonl"
            cases = [
                FailureCase(task="detection", sample_id=f"img_{i:03d}", failure_type="false_negative")
                for i in range(3)
            ]
            with open(out, "w") as f:
                for fc in cases:
                    f.write(json.dumps(fc.to_dict()) + "\n")

            lines = out.read_text().strip().splitlines()
            assert len(lines) == 3
            for line in lines:
                d = json.loads(line)
                assert "task" in d
                assert "failure_type" in d
