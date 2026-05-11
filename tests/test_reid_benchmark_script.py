from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_reid_script_missing_dataset_exits_cleanly(tmp_path):
    script = _root() / "scripts" / "evaluate_reid_models.py"
    missing = tmp_path / "nope"
    r = subprocess.run(
        [sys.executable, str(script), "--dataset-root", str(missing)],
        cwd=str(_root()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 2
    assert "dataset missing" in (r.stderr + r.stdout).lower()
