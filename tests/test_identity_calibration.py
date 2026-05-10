from __future__ import annotations

from scripts.calibrate_identity_thresholds import calibrate_thresholds, write_calibration_outputs


def test_threshold_sweep_computes_far_frr(tmp_path):
    pair_results = (
        [{"same": True, "similarity": 0.95}] * 20
        + [{"same": True, "similarity": 0.88}] * 20
        + [{"same": False, "similarity": 0.10}] * 30
        + [{"same": False, "similarity": 0.22}] * 10
    )
    result = calibrate_thresholds(pair_results)
    assert "metrics" in result
    assert result["metrics"]["far"] is not None
    assert result["metrics"]["frr"] is not None
    out_dir = write_calibration_outputs(result, tmp_path / "calibration")
    assert (out_dir / "metrics.json").exists()
    assert (out_dir / "threshold_sweep.csv").exists()
    assert (out_dir / "roc_curve.csv").exists()
