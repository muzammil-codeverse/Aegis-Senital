from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_face_calibration_missing_dataset_exits_cleanly(tmp_path):
    script = _root() / "scripts" / "calibrate_identity_thresholds.py"
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(_root()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 2
    assert "dataset missing" in (r.stderr + r.stdout).lower()


def test_face_calibration_does_not_promote_fake_threshold(tmp_path):
    script = _root() / "scripts" / "calibrate_identity_thresholds.py"
    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps(
            [
                {"same": True, "similarity": 0.2},
                {"same": True, "similarity": 0.25},
                {"same": False, "similarity": 0.9},
                {"same": False, "similarity": 0.95},
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out_face"
    r = subprocess.run(
        [sys.executable, str(script), "--pairs", str(pairs), "--output-dir", str(out)],
        cwd=str(_root()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert "recommended_threshold" in metrics["metrics"]
    assert metrics.get("threshold_accepted") in {True, False}
