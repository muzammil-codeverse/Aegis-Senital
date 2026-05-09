"""
Phase 25 — Benchmark comparison script.

Usage:
    python scripts/compare_benchmarks.py \
        --baseline storage/evaluation_runs/run_2026_05_09_001 \
        --candidate storage/evaluation_runs/run_2026_05_09_002 \
        --output storage/evaluation_runs/comparisons/compare_001_002.md
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("compare_benchmarks")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 25 — Benchmark comparison")
    parser.add_argument("--baseline", required=True, help="Path to baseline run directory")
    parser.add_argument("--candidate", required=True, help="Path to candidate run directory")
    parser.add_argument(
        "--output",
        default=None,
        help="Output comparison report path (.md) — defaults to comparisons/ subdir",
    )
    parser.add_argument(
        "--config",
        default="configs/evaluation/evaluation.yaml",
        help="Evaluation config for regression policy",
    )
    args = parser.parse_args()

    from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
    from backend.app.evaluation.benchmark_config import load_regression_policy

    regression_policy = {}
    try:
        from backend.app.evaluation.benchmark_config import load_evaluation_config
        config = load_evaluation_config(args.config)
        regression_policy = load_regression_policy(config)
    except FileNotFoundError:
        logger.warning("Evaluation config not found — using default regression policy")

    comparator = BenchmarkComparator(regression_policy=regression_policy)

    try:
        comparison = comparator.compare(args.baseline, args.candidate)
    except FileNotFoundError as exc:
        logger.error("Cannot compare runs: %s", exc)
        return 1

    output_path = args.output
    if not output_path:
        baseline_name = Path(args.baseline).name
        candidate_name = Path(args.candidate).name
        output_dir = Path("storage/evaluation_runs/comparisons")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"compare_{baseline_name}_{candidate_name}.md")

    comparator.write_report(comparison, output_path)

    print(f"\n{'='*60}")
    print(f"Baseline:  {comparison.baseline_run_id}")
    print(f"Candidate: {comparison.candidate_run_id}")
    print(f"Status:    {comparison.overall_status.upper()}")
    print(f"Deltas:    {len(comparison.deltas)}")
    print(f"Report:    {output_path}")

    regressions = [d for d in comparison.deltas if d.status == "regressed"]
    if regressions:
        print(f"\nRegressions ({len(regressions)}):")
        for r in regressions[:10]:
            print(f"  {r.metric}: {r.baseline} → {r.candidate} ({r.absolute_change:+.4f})")

    return 0 if comparison.overall_status in ("pass", "warn") else 1


if __name__ == "__main__":
    sys.exit(main())
