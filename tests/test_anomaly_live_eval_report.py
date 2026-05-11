from __future__ import annotations

from pathlib import Path


def test_eval_script_report_documents_offline_separation():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "evaluate_anomaly_live_video.py").read_text(encoding="utf-8")
    assert "_offline_predict" in text
    assert "Offline `_offline_predict` results are not live inference metrics." in text


def test_anomaly_benchmark_still_uses_offline_predict():
    root = Path(__file__).resolve().parents[1]
    text = (root / "backend" / "app" / "evaluation" / "runners" / "anomaly_benchmark_runner.py").read_text(encoding="utf-8")
    assert "_offline_predict" in text
