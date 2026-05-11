from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_eval_module():
    path = ROOT / "scripts" / "evaluate_anomaly_live_video.py"
    spec = importlib.util.spec_from_file_location("evaluate_anomaly_live_video", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_live_eval_writes_metrics_and_report(tmp_path, monkeypatch):
    ev = _load_eval_module()
    vid = tmp_path / "v.avi"
    vid.write_bytes(b"not-a-real-video")

    def fake_evaluate(**kwargs):
        return {
            "video": str(kwargs["video_path"]),
            "frame_count_decoded": 10,
            "latency_ms": 12.5,
            "live_inference": {"model": None, "violence": None, "rule_engine_count": 0},
            "provider_status": {"video_model_loaded": False, "violence_requested": False},
        }

    monkeypatch.setattr(ev, "_evaluate_one_video", fake_evaluate)
    monkeypatch.setattr(ev, "_collect_videos", lambda videos_arg, manifest: [{"path": vid, "label": None, "source": "test"}])

    out = tmp_path / "out"
    argv = [
        "evaluate_anomaly_live_video.py",
        "--videos",
        str(vid),
        "--model-path",
        str(tmp_path / "model"),
        "--device",
        "cpu",
        "--output-dir",
        str(out),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    code = ev.main()
    assert code in (0, 1)
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["note"].startswith("Offline")
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "Live inference" in report or "live inference" in report.lower()
    assert (out / "per_video_predictions.jsonl").is_file()
    assert (out / "latency_profile.json").is_file()
