"""
Phase 25 — Runtime latency profiling script.

Usage:
    python scripts/profile_runtime_latency.py \
        --config configs/evaluation/evaluation.yaml \
        --input samples/videos/test_stream.mp4 \
        --duration-seconds 120 \
        --device cuda
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("profile_runtime_latency")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 25 — Runtime latency profiling")
    parser.add_argument(
        "--config",
        default="configs/evaluation/evaluation.yaml",
        help="Evaluation config YAML",
    )
    parser.add_argument(
        "--input",
        default="samples/videos/test_stream.mp4",
        help="Input video file or RTSP stream URL",
    )
    parser.add_argument("--duration-seconds", type=int, default=120, help="Profile duration in seconds")
    parser.add_argument("--device", default=None, help="cuda or cpu (overrides config)")
    parser.add_argument("--output-dir", default="storage/evaluation_runs", help="Output directory")
    args = parser.parse_args()

    from backend.app.evaluation.benchmark_config import (
        load_evaluation_config, resolve_device, get_git_commit,
        config_hash, save_config_snapshot,
    )
    from backend.app.evaluation.runners.system_latency_runner import SystemLatencyRunner
    from backend.app.evaluation.reports.report_writer import ReportWriter
    from backend.app.evaluation.schemas import BenchmarkRun

    try:
        config = load_evaluation_config(args.config)
    except FileNotFoundError:
        logger.warning("Config not found — using defaults")
        config = {}

    device = resolve_device(config, args.device)
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y_%m_%d_%H%M%S')}_latency"
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    save_config_snapshot(run_dir, config)

    runner = SystemLatencyRunner(device=device, duration_seconds=args.duration_seconds)
    task_result = runner.run(input_path=args.input, run_dir=run_dir)

    run = BenchmarkRun(
        run_id=run_id,
        git_commit=get_git_commit(),
        config_hash=config_hash(config),
        config_snapshot=config,
        device=device,
        task_results=[task_result],
    )
    ReportWriter().write(run, run_dir)

    print(f"\n{'='*60}")
    print(f"Run ID:   {run_id}")
    print(f"Output:   {run_dir}")

    if task_result.skipped:
        print(f"[SKIPPED] {task_result.skip_reason}")
        return 1

    m = task_result.metrics
    print(f"FPS:      {m.get('avg_fps', '—')}")
    print(f"Dropped:  {m.get('dropped_frames', 0)} frames")
    for stage in m.get("stages", []):
        print(f"  {stage['stage']}: p95={stage.get('p95_ms')} ms, p99={stage.get('p99_ms')} ms")

    return 0


if __name__ == "__main__":
    sys.exit(main())
