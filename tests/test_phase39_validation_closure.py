from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_evaluate_anomaly_live_video_script_importable():
    path = _root() / "scripts" / "evaluate_anomaly_live_video.py"
    spec = importlib.util.spec_from_file_location("evaluate_anomaly_live_video", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(getattr(mod, "main", None))


def test_smoke_uploaded_video_script_exists():
    script = _root() / "scripts" / "smoke_uploaded_video_workflow.py"
    assert script.is_file()


def test_evaluate_anomaly_live_video_help_runs():
    script = _root() / "scripts" / "evaluate_anomaly_live_video.py"
    r = subprocess.run([sys.executable, str(script), "-h"], cwd=str(_root()), capture_output=True, text=True)
    assert r.returncode in {0, 2}
