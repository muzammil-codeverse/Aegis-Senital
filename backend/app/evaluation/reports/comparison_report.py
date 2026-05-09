"""Phase 25 — Benchmark comparison tool (baseline vs candidate)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.app.evaluation.schemas import BenchmarkComparison, MetricDelta

logger = logging.getLogger(__name__)

# Metric keys considered "higher is better"
_HIGHER_IS_BETTER = {
    "map_50", "map_50_95", "precision", "recall", "f1",
    "rank_1", "rank_5", "map",
    "mota", "motp", "idf1",
    "tar", "far",
    "avg_fps",
    "merge_precision", "merge_recall",
}

# Metric keys considered "lower is better"
_LOWER_IS_BETTER = {
    "false_positives_per_image", "false_negatives_per_image",
    "frr", "id_switches", "fragmentation",
    "false_merge_rate", "false_split_rate",
    "dropped_frames",
    "p95_ms", "p99_ms", "avg_ms",
}


class BenchmarkComparator:

    def __init__(self, regression_policy: dict | None = None) -> None:
        self._policy = regression_policy or {
            "detection_map_drop_warn": 0.02,
            "detection_map_drop_fail": 0.05,
            "latency_p95_increase_warn_percent": 15,
            "latency_p95_increase_fail_percent": 30,
            "false_positive_increase_warn_percent": 20,
        }

    def compare(
        self,
        baseline_dir: str | Path,
        candidate_dir: str | Path,
    ) -> BenchmarkComparison:
        baseline_dir = Path(baseline_dir)
        candidate_dir = Path(candidate_dir)

        baseline = self._load_run(baseline_dir)
        candidate = self._load_run(candidate_dir)

        baseline_id = baseline.get("run_id", baseline_dir.name)
        candidate_id = candidate.get("run_id", candidate_dir.name)

        deltas = self._compute_deltas(baseline, candidate)
        overall_status = self._evaluate_policy(deltas)

        return BenchmarkComparison(
            baseline_run_id=baseline_id,
            candidate_run_id=candidate_id,
            deltas=deltas,
            overall_status=overall_status,
            regression_policy=self._policy,
        )

    def _load_run(self, run_dir: Path) -> dict:
        metrics_file = run_dir / "metrics.json"
        if not metrics_file.exists():
            raise FileNotFoundError(f"metrics.json not found in {run_dir}")
        with open(metrics_file, encoding="utf-8") as f:
            return json.load(f)

    def _compute_deltas(self, baseline: dict, candidate: dict) -> list[MetricDelta]:
        deltas = []

        # Flatten task metrics
        baseline_flat = self._flatten_metrics(baseline)
        candidate_flat = self._flatten_metrics(candidate)

        all_keys = set(baseline_flat.keys()) | set(candidate_flat.keys())
        for key in sorted(all_keys):
            b_val = baseline_flat.get(key)
            c_val = candidate_flat.get(key)

            if b_val is None and c_val is None:
                continue
            if not isinstance(b_val, (int, float)) or not isinstance(c_val, (int, float)):
                continue

            abs_change = c_val - b_val
            pct_change = abs_change / abs(b_val) * 100.0 if b_val != 0 else None

            status = self._classify(key, abs_change, pct_change)
            deltas.append(MetricDelta(
                metric=key,
                baseline=round(b_val, 4),
                candidate=round(c_val, 4),
                absolute_change=round(abs_change, 4),
                percent_change=round(pct_change, 2) if pct_change is not None else None,
                status=status,
            ))

        return deltas

    def _flatten_metrics(self, run: dict) -> dict[str, float]:
        flat = {}
        for tr in run.get("task_results", []):
            task = tr.get("task", "unknown")
            if tr.get("skipped"):
                continue
            for key, val in tr.get("metrics", {}).items():
                if isinstance(val, (int, float)):
                    flat[f"{task}.{key}"] = float(val)
                elif isinstance(val, dict):
                    for sub_key, sub_val in val.items():
                        if isinstance(sub_val, (int, float)):
                            flat[f"{task}.{key}.{sub_key}"] = float(sub_val)
        return flat

    def _classify(self, key: str, abs_change: float, pct_change: float | None) -> str:
        metric_short = key.split(".")[-1]
        if metric_short in _HIGHER_IS_BETTER:
            if abs_change > 0:
                return "improved"
            if abs_change < 0:
                return "regressed"
        elif metric_short in _LOWER_IS_BETTER:
            if abs_change < 0:
                return "improved"
            if abs_change > 0:
                return "regressed"
        return "unchanged"

    def _evaluate_policy(self, deltas: list[MetricDelta]) -> str:
        status = "pass"
        map_drop_warn = self._policy.get("detection_map_drop_warn", 0.02)
        map_drop_fail = self._policy.get("detection_map_drop_fail", 0.05)
        lat_warn = self._policy.get("latency_p95_increase_warn_percent", 15)
        lat_fail = self._policy.get("latency_p95_increase_fail_percent", 30)

        for delta in deltas:
            metric = delta.metric
            if "map_50" in metric and delta.absolute_change is not None:
                if delta.absolute_change < -map_drop_fail:
                    status = "fail"
                elif delta.absolute_change < -map_drop_warn and status != "fail":
                    status = "warn"
            if "p95" in metric and delta.percent_change is not None:
                if delta.percent_change > lat_fail:
                    status = "fail"
                elif delta.percent_change > lat_warn and status != "fail":
                    status = "warn"

        return status

    def write_report(self, comparison: BenchmarkComparison, output_path: str | Path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# Benchmark Comparison Report",
            "",
            f"**Baseline:** {comparison.baseline_run_id}  ",
            f"**Candidate:** {comparison.candidate_run_id}  ",
            f"**Overall status:** `{comparison.overall_status.upper()}`  ",
            f"**Timestamp:** {comparison.timestamp}  ",
            "",
            "## Metric Deltas",
            "",
            "| Metric | Baseline | Candidate | Change | % Change | Status |",
            "|--------|----------|-----------|--------|----------|--------|",
        ]

        for d in comparison.deltas:
            pct = f"{d.percent_change:+.2f}%" if d.percent_change is not None else "—"
            change = f"{d.absolute_change:+.4f}" if d.absolute_change is not None else "—"
            status_icon = {"improved": "✓", "regressed": "✗", "unchanged": "—"}.get(d.status, "—")
            lines.append(
                f"| {d.metric} | {d.baseline} | {d.candidate} | {change} | {pct} | {status_icon} {d.status} |"
            )

        if comparison.warnings:
            lines += ["", "## Warnings", ""]
            for w in comparison.warnings:
                lines.append(f"- {w}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        # Also write JSON
        json_path = output_path.with_suffix(".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(comparison.to_dict(), f, indent=2, default=str)

        logger.info("Comparison report written to %s", output_path)
