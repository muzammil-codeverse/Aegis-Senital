"""
Evaluate anomaly detection models against prepared datasets.

Usage:
    python scripts/evaluate_anomaly_models.py --split test
    python scripts/evaluate_anomaly_models.py --split test --dataset-dir datasets/training/anomaly_video
    python scripts/evaluate_anomaly_models.py --check-policy

GPU check is performed before any inference to ensure CUDA is available.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _check_gpu() -> None:
    try:
        import torch
        if not torch.cuda.is_available():
            logger.error(
                "CUDA not available. torch.cuda.is_available() = False.\n"
                "Fix the CUDA/PyTorch environment before running evaluation.\n"
                "Install: pip install torch --index-url https://download.pytorch.org/whl/cu124"
            )
            sys.exit(1)
        device_name = torch.cuda.get_device_name(0)
        logger.info("GPU confirmed: %s", device_name)
    except ImportError:
        logger.warning("torch not installed; GPU check skipped. Evaluation will run on CPU.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate anomaly detection models")
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--dataset-dir", default="datasets/training/anomaly_video")
    parser.add_argument("--output-dir", default="storage/evaluation_runs/anomaly")
    parser.add_argument("--check-policy", action="store_true", help="Print acceptance policy and exit")
    parser.add_argument("--skip-gpu-check", action="store_true", help="Skip GPU availability check")
    args = parser.parse_args()

    if args.check_policy:
        from inference.anomaly.config import load_anomaly_config
        cfg = load_anomaly_config()
        policy = cfg.get("acceptance_policy", {})
        print("\nAnomaly Acceptance Policy:")
        for k, v in policy.items():
            print(f"  {k}: {v}")
        return

    if not args.skip_gpu_check:
        _check_gpu()

    from backend.app.evaluation.runners.anomaly_benchmark_runner import AnomalyBenchmarkRunner

    runner = AnomalyBenchmarkRunner(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
    )
    result = runner.run(split=args.split)

    if result is None:
        logger.error("Benchmark produced no result (dataset may be missing).")
        sys.exit(1)

    print("\n=== Anomaly Benchmark Results ===")
    import json as _json
    print(_json.dumps(result.to_dict(), indent=2))

    if not result.passed:
        logger.error("Benchmark FAILED acceptance policy.")
        sys.exit(2)
    else:
        logger.info("Benchmark PASSED acceptance policy.")


if __name__ == "__main__":
    main()
