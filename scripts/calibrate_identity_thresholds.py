#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.evaluation.metrics.face_metrics import compute_face_metrics

ACCEPTANCE_POLICY = {
    "max_far_at_operating_threshold": 0.01,
    "max_frr_at_operating_threshold": 0.10,
    "min_tar_at_far_1e_2": 0.85,
}


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def load_pair_results(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    if file_path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if file_path.suffix.lower() == ".json":
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        raise ValueError("JSON input must be a list of pair result objects.")
    if file_path.suffix.lower() == ".csv":
        rows = []
        with file_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(
                    {
                        "same": str(row.get("same", "")).lower() in {"1", "true", "yes"},
                        "similarity": float(row.get("similarity", row.get("score", 0.0)) or 0.0),
                    }
                )
        return rows
    raise ValueError(f"Unsupported pair-results format: {file_path.suffix}")


def build_distance_histogram(pair_results: list[dict[str, Any]], bins: int = 20) -> dict[str, list[dict[str, Any]]]:
    same_scores = [1.0 - float(row["similarity"]) for row in pair_results if row.get("same")]
    diff_scores = [1.0 - float(row["similarity"]) for row in pair_results if not row.get("same")]

    def _hist(values: list[float]) -> list[dict[str, Any]]:
        if not values:
            return []
        low, high = min(values), max(values)
        if low == high:
            return [{"bin_start": round(low, 4), "bin_end": round(high, 4), "count": len(values)}]
        width = (high - low) / bins
        hist = []
        for index in range(bins):
            start = low + index * width
            end = high if index == bins - 1 else start + width
            if index == bins - 1:
                count = sum(1 for value in values if start <= value <= end)
            else:
                count = sum(1 for value in values if start <= value < end)
            hist.append({"bin_start": round(start, 4), "bin_end": round(end, 4), "count": count})
        return hist

    return {
        "same_person": _hist(same_scores),
        "different_person": _hist(diff_scores),
    }


def calibrate_thresholds(pair_results: list[dict[str, Any]]) -> dict[str, Any]:
    metric_result = compute_face_metrics(pair_results, far_thresholds=[1e-2])
    tar_at_far = float(metric_result.tar_at_far_thresholds.get("FAR=1e-02", 0.0))
    accepted = (
        metric_result.far is not None
        and metric_result.frr is not None
        and metric_result.far <= ACCEPTANCE_POLICY["max_far_at_operating_threshold"]
        and metric_result.frr <= ACCEPTANCE_POLICY["max_frr_at_operating_threshold"]
        and tar_at_far >= ACCEPTANCE_POLICY["min_tar_at_far_1e_2"]
    )
    return {
        "metrics": metric_result.to_dict(),
        "distance_histogram": build_distance_histogram(pair_results),
        "acceptance_policy": ACCEPTANCE_POLICY,
        "threshold_accepted": bool(accepted),
    }


def write_calibration_outputs(result: dict[str, Any], output_dir: str | Path) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    sweep = result["metrics"].get("threshold_sweep", [])
    if sweep:
        with (out_dir / "threshold_sweep.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(sweep[0].keys()))
            writer.writeheader()
            writer.writerows(sweep)

    roc_curve = result["metrics"].get("roc_curve_points", [])
    if roc_curve:
        with (out_dir / "roc_curve.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(roc_curve[0].keys()))
            writer.writeheader()
            writer.writerows(roc_curve)

    report = out_dir / "report.md"
    metrics = result["metrics"]
    report.write_text(
        "\n".join(
            [
                "# Identity Calibration Report",
                "",
                f"- FAR: {metrics.get('far')}",
                f"- FRR: {metrics.get('frr')}",
                f"- TAR@FAR=1e-2: {metrics.get('tar_at_far_thresholds', {}).get('FAR=1e-02')}",
                f"- Recommended threshold: {metrics.get('recommended_threshold')}",
                f"- Threshold accepted: {result.get('threshold_accepted')}",
                "",
                "Operator review remains required for live identity decisions.",
            ]
        ),
        encoding="utf-8",
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", required=True, help="Path to JSON/JSONL/CSV pair results.")
    parser.add_argument(
        "--output-dir",
        default=str(Path("storage") / "evaluation_runs" / f"identity_calibration_{_now_stamp()}"),
        help="Output directory for calibration artifacts.",
    )
    args = parser.parse_args()

    pair_results = load_pair_results(args.pairs)
    result = calibrate_thresholds(pair_results)
    out_dir = write_calibration_outputs(result, args.output_dir)
    print(json.dumps({"status": "ok", "output_dir": str(out_dir), "threshold_accepted": result["threshold_accepted"]}, indent=2))


if __name__ == "__main__":
    main()
