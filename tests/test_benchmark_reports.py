"""
Phase 25 — Tests for benchmark report writing and config loading.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


class TestReportWriter:

    def _make_run(self):
        from backend.app.evaluation.schemas import BenchmarkRun, BenchmarkTaskResult
        run = BenchmarkRun(
            run_id="test_run_001",
            git_commit="abc123",
            config_hash="deadbeef",
            device="cpu",
        )
        run.task_results.append(BenchmarkTaskResult(
            task="detection",
            model_name="weapon_yolo",
            model_path="models/weapon.pt",
            device="cpu",
            dataset_name="weapon_eval",
            metrics={"map_50": 0.72, "precision": 0.81, "recall": 0.68},
            failure_cases_count=5,
        ))
        return run

    def test_write_creates_metrics_json(self):
        from backend.app.evaluation.reports.report_writer import ReportWriter
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "test_run"
            run = self._make_run()
            writer = ReportWriter()
            artifacts = writer.write(run, run_dir)
            assert "metrics_json" in artifacts
            metrics_path = Path(artifacts["metrics_json"])
            assert metrics_path.exists()
            with open(metrics_path) as f:
                data = json.load(f)
            assert data["run_id"] == "test_run_001"

    def test_write_creates_report_md(self):
        from backend.app.evaluation.reports.report_writer import ReportWriter
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "test_run"
            run = self._make_run()
            writer = ReportWriter()
            artifacts = writer.write(run, run_dir)
            assert "report_md" in artifacts
            report_path = Path(artifacts["report_md"])
            assert report_path.exists()
            content = report_path.read_text()
            assert "test_run_001" in content
            assert "detection" in content.lower()

    def test_skipped_task_in_report(self):
        from backend.app.evaluation.schemas import BenchmarkRun, BenchmarkTaskResult
        from backend.app.evaluation.reports.report_writer import ReportWriter
        with tempfile.TemporaryDirectory() as tmp:
            run = BenchmarkRun(run_id="skip_test", device="cpu")
            run.task_results.append(BenchmarkTaskResult(
                task="tracking",
                model_name="tracker",
                dataset_name="mot_eval",
                skipped=True,
                skip_reason="Dataset not found",
            ))
            writer = ReportWriter()
            artifacts = writer.write(run, Path(tmp) / "skip_run")
            report = Path(artifacts["report_md"]).read_text()
            assert "SKIPPED" in report
            assert "Dataset not found" in report

    def test_config_snapshot_saved(self):
        from backend.app.evaluation.benchmark_config import save_config_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            config = {"evaluation": {"device": "cpu"}, "regression_policy": {"detection_map_drop_fail": 0.05}}
            save_config_snapshot(run_dir, config)
            snap = run_dir / "config_snapshot.yaml"
            assert snap.exists()
            content = snap.read_text()
            assert "evaluation" in content

    def test_run_serializable_to_json(self):
        run = self._make_run()
        data = run.to_dict()
        json_str = json.dumps(data, default=str)
        assert "test_run_001" in json_str


class TestBenchmarkConfig:

    def test_config_hash_deterministic(self):
        from backend.app.evaluation.benchmark_config import config_hash
        config = {"a": 1, "b": [2, 3]}
        h1 = config_hash(config)
        h2 = config_hash(config)
        assert h1 == h2

    def test_config_hash_changes_with_content(self):
        from backend.app.evaluation.benchmark_config import config_hash
        h1 = config_hash({"a": 1})
        h2 = config_hash({"a": 2})
        assert h1 != h2

    def test_load_evaluation_config(self):
        from backend.app.evaluation.benchmark_config import load_evaluation_config
        config_path = Path("configs/evaluation/evaluation.yaml")
        if not config_path.exists():
            pytest.skip("Evaluation config not found")
        config = load_evaluation_config(config_path)
        assert "evaluation" in config

    def test_load_config_missing_file_raises(self):
        from backend.app.evaluation.benchmark_config import load_evaluation_config
        with pytest.raises(FileNotFoundError):
            load_evaluation_config("nonexistent/path/config.yaml")

    def test_resolve_device_cpu_fallback(self):
        from backend.app.evaluation.benchmark_config import resolve_device
        config = {"evaluation": {"device": "cuda", "allow_cpu_fallback": True}}
        device = resolve_device(config, override="cpu")
        assert device == "cpu"

    def test_resolve_device_override(self):
        from backend.app.evaluation.benchmark_config import resolve_device
        config = {}
        assert resolve_device(config, override="cpu") == "cpu"
