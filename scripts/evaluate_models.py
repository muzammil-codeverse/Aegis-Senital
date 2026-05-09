"""
Phase 25 — Model evaluation script.

Usage:
    python scripts/evaluate_models.py \
        --task detection \
        --config configs/evaluation/evaluation.yaml \
        --dataset weapon_eval \
        --model weapon_yolo \
        --device cuda

    python scripts/evaluate_models.py --task detection --device cpu
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("evaluate_models")

SUPPORTED_TASKS = ["detection", "tracking", "face", "reid", "identity_fusion", "open_vocab", "latency"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 25 — Model evaluation runner")
    parser.add_argument("--task", required=True, choices=SUPPORTED_TASKS, help="Evaluation task")
    parser.add_argument(
        "--config",
        default="configs/evaluation/evaluation.yaml",
        help="Evaluation config YAML",
    )
    parser.add_argument("--dataset", default=None, help="Dataset name from config")
    parser.add_argument("--model", default=None, help="Model name from config")
    parser.add_argument("--device", default=None, help="cuda or cpu (overrides config)")
    parser.add_argument("--output-dir", default=None, help="Override output directory")
    parser.add_argument("--no-failure-cases", action="store_true", help="Skip failure case export")
    args = parser.parse_args()

    from backend.app.evaluation.benchmark_config import (
        load_evaluation_config, resolve_device, get_git_commit,
        config_hash, make_run_dir, save_config_snapshot,
    )
    from backend.app.evaluation.datasets.dataset_registry import DatasetRegistry
    from backend.app.evaluation.reports.report_writer import ReportWriter
    from backend.app.evaluation.schemas import BenchmarkRun

    try:
        config = load_evaluation_config(args.config)
    except FileNotFoundError as exc:
        logger.error("Config file not found: %s", exc)
        return 1

    device = resolve_device(config, args.device)
    logger.info("Device: %s", device)

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y_%m_%d_%H%M%S')}_{args.task}"
    if args.output_dir:
        from pathlib import Path as P
        run_dir = P(args.output_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = make_run_dir(config, run_id)

    save_config_snapshot(run_dir, config)

    registry = DatasetRegistry(config)

    run = BenchmarkRun(
        run_id=run_id,
        git_commit=get_git_commit(),
        config_hash=config_hash(config),
        config_snapshot=config,
        device=device,
    )

    task_result = None
    save_failures = not args.no_failure_cases and config.get("evaluation", {}).get("save_failure_cases", True)

    if args.task == "detection":
        task_result = _run_detection(args, config, registry, device, run_dir, save_failures)

    elif args.task == "tracking":
        task_result = _run_tracking(args, config, registry, device, run_dir, save_failures)

    elif args.task in ("face", "reid", "identity_fusion"):
        task_result = _run_identity(args, config, registry, device, run_dir)

    elif args.task == "open_vocab":
        task_result = _run_open_vocab(args, config, registry, device, run_dir)

    elif args.task == "latency":
        task_result = _run_latency(args, config, device, run_dir)

    if task_result:
        run.task_results.append(task_result)

    writer = ReportWriter()
    artifacts = writer.write(run, run_dir)

    print(f"\n{'='*60}")
    print(f"Run ID:     {run.run_id}")
    print(f"Output:     {run_dir}")
    print(f"Device:     {device}")
    for name, path in artifacts.items():
        print(f"  {name}: {path}")

    if task_result and not task_result.skipped:
        print(f"\nMetrics summary ({args.task}):")
        for k, v in task_result.metrics.items():
            if isinstance(v, (int, float)):
                print(f"  {k}: {v}")
    elif task_result and task_result.skipped:
        print(f"\n[SKIPPED] {task_result.skip_reason}")

    return 0


def _run_detection(args, config, registry, device, run_dir, save_failures):
    from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
    from backend.app.evaluation.datasets.coco_yolo_loader import CocoYoloLoader

    dataset_name = args.dataset or config.get("evaluation", {}).get("default_detection_dataset", "weapon_eval")
    model_name = args.model or "weapon_yolo"

    try:
        dataset_entry = registry.get_required(dataset_name)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        from backend.app.evaluation.schemas import BenchmarkTaskResult
        return BenchmarkTaskResult(
            task="detection", model_name=model_name, dataset_name=dataset_name,
            skipped=True, skip_reason=str(exc),
        )

    class_names = config.get("datasets", {}).get(dataset_name, {}).get("class_names", ["weapon", "phone", "person"])
    loader = CocoYoloLoader(dataset_entry.path, class_names=class_names)
    samples = loader.load_yolo_annotations()

    if not samples:
        from backend.app.evaluation.schemas import BenchmarkTaskResult
        return BenchmarkTaskResult(
            task="detection", model_name=model_name, dataset_name=dataset_name,
            skipped=True, skip_reason="No samples loaded from dataset path",
        )

    # Build predict function (stub — integrate with real model when available)
    def predict_fn(image_path):
        logger.debug("Predicting on %s", image_path)
        return []  # No fake detections — return empty until real model is wired in

    model_path = config.get("models", {}).get(model_name, {}).get("path", "")
    runner = DetectionBenchmarkRunner(
        model_name=model_name,
        model_path=model_path,
        device=device,
    )
    return runner.run(
        samples=samples,
        predict_fn=predict_fn,
        dataset_name=dataset_name,
        class_names=class_names,
        run_dir=run_dir,
        save_failure_cases=save_failures,
    )


def _run_tracking(args, config, registry, device, run_dir, save_failures):
    from backend.app.evaluation.runners.tracking_benchmark_runner import TrackingBenchmarkRunner
    from backend.app.evaluation.datasets.mot_loader import MOTLoader

    dataset_name = args.dataset or "mot_eval"
    try:
        entry = registry.get_required(dataset_name)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        from backend.app.evaluation.schemas import BenchmarkTaskResult
        return BenchmarkTaskResult(
            task="tracking", model_name="stream_tracker", dataset_name=dataset_name,
            skipped=True, skip_reason=str(exc),
        )

    loader = MOTLoader(entry.path)
    gt = loader.load_ground_truth()
    gt_by_frame = loader.group_by_frame(gt)
    runner = TrackingBenchmarkRunner(device=device)
    return runner.run(
        gt_by_frame=gt_by_frame,
        pred_by_frame={},
        dataset_name=dataset_name,
        run_dir=run_dir,
        save_failure_cases=save_failures,
    )


def _run_identity(args, config, registry, device, run_dir):
    from backend.app.evaluation.schemas import BenchmarkTaskResult
    task = args.task
    if task == "face":
        from backend.app.evaluation.runners.identity_benchmark_runner import FaceBenchmarkRunner
        runner = FaceBenchmarkRunner(device=device)
        return runner.run(pair_results=[], dataset_name=args.dataset or "face_eval", run_dir=run_dir)
    if task == "reid":
        from backend.app.evaluation.runners.identity_benchmark_runner import ReIDBenchmarkRunner
        runner = ReIDBenchmarkRunner(device=device)
        return runner.run(query_embeddings=[], gallery_embeddings=[], dataset_name=args.dataset or "reid_eval", run_dir=run_dir)
    if task == "identity_fusion":
        from backend.app.evaluation.runners.identity_benchmark_runner import IdentityFusionBenchmarkRunner
        runner = IdentityFusionBenchmarkRunner()
        return runner.run(scenario_results={}, merge_events=None, dataset_name=args.dataset or "identity_fusion")
    return None


def _run_open_vocab(args, config, registry, device, run_dir):
    from backend.app.evaluation.runners.open_vocab_benchmark_runner import OpenVocabBenchmarkRunner
    dataset_name = args.dataset or "open_vocab_eval"
    runner = OpenVocabBenchmarkRunner(device=device)
    prompt_configs = config.get("open_vocab_eval", {}).get("prompts", [])

    try:
        entry = registry.get_required(dataset_name)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        from backend.app.evaluation.schemas import BenchmarkTaskResult
        return BenchmarkTaskResult(
            task="open_vocab", model_name="grounding_dino", dataset_name=dataset_name,
            skipped=True, skip_reason=str(exc),
        )

    from backend.app.evaluation.datasets.open_vocab_eval_loader import OpenVocabEvalLoader
    loader = OpenVocabEvalLoader(entry.path)
    samples = loader.load()
    by_prompt = loader.group_by_prompt(samples)

    def predict_fn(image_path, prompt_text, threshold):
        return []  # No fake detections

    return runner.run(
        samples_by_prompt=by_prompt,
        predict_fn=predict_fn,
        prompt_configs=prompt_configs,
        dataset_name=dataset_name,
        run_dir=run_dir,
    )


def _run_latency(args, config, device, run_dir):
    from backend.app.evaluation.runners.system_latency_runner import SystemLatencyRunner
    input_path = config.get("evaluation", {}).get("latency_test_input", "samples/videos/test_stream.mp4")
    duration = config.get("evaluation", {}).get("latency_duration_seconds", 60)
    runner = SystemLatencyRunner(device=device, duration_seconds=duration)
    return runner.run(input_path=input_path, run_dir=run_dir)


if __name__ == "__main__":
    sys.exit(main())
