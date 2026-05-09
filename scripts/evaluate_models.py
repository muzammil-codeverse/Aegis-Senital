"""
Phase 25/26 — Model evaluation script.

Usage:
    # Single model
    python scripts/evaluate_models.py \
        --task detection \
        --dataset weapon_eval \
        --model weapon_yolov8_baseline \
        --device cuda

    # Multi-model head-to-head with auto-comparison
    python scripts/evaluate_models.py \
        --task detection \
        --dataset weapon_eval \
        --models weapon_yolov8_baseline weapon_yolo11_candidate \
        --compare

    # Other tasks
    python scripts/evaluate_models.py --task tracking --dataset mot_eval
    python scripts/evaluate_models.py --task face --dataset face_eval
    python scripts/evaluate_models.py --task reid --dataset reid_eval
    python scripts/evaluate_models.py --task open_vocab --dataset open_vocab_eval
    python scripts/evaluate_models.py --task latency
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("evaluate_models")

SUPPORTED_TASKS = ["detection", "tracking", "face", "reid", "identity_fusion", "open_vocab", "latency"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 25/26 — Model evaluation runner")
    parser.add_argument("--task", required=True, choices=SUPPORTED_TASKS)
    parser.add_argument("--config", default="configs/evaluation/evaluation.yaml")
    parser.add_argument("--dataset", default=None, help="Dataset name from config")
    # Single-model mode
    parser.add_argument("--model", default=None, help="Single model name from config")
    # Multi-model mode (Phase 26)
    parser.add_argument("--models", nargs="+", default=None, help="Multiple model names for head-to-head")
    parser.add_argument("--compare", action="store_true", help="Auto-compare all --models runs")
    parser.add_argument("--device", default=None, help="cuda or cpu (overrides config)")
    parser.add_argument("--output-dir", default=None, help="Override output directory")
    parser.add_argument("--no-failure-cases", action="store_true")
    parser.add_argument("--map-50-95", action="store_true", help="Compute mAP@0.5:0.95 (slower)")
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

    # Resolve model list
    model_names: list[str] = []
    if args.models:
        model_names = args.models
    elif args.model:
        model_names = [args.model]
    else:
        model_names = [None]  # single anonymous run

    save_failures = not args.no_failure_cases and config.get("evaluation", {}).get("save_failure_cases", True)
    registry = DatasetRegistry(config)

    # Run each model separately
    run_dirs: list[Path] = []
    model_metric_summaries: list[dict] = []

    for model_name in model_names:
        ts = datetime.now(timezone.utc).strftime("%Y_%m_%d_%H%M%S")
        run_id = f"run_{ts}_{args.task}"
        if model_name:
            run_id = f"{run_id}_{model_name}"

        if args.output_dir:
            run_dir = Path(args.output_dir) / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
        else:
            run_dir = make_run_dir(config, run_id)

        save_config_snapshot(run_dir, config)

        run = BenchmarkRun(
            run_id=run_id,
            git_commit=get_git_commit(),
            config_hash=config_hash(config),
            config_snapshot=config,
            device=device,
        )

        task_result = None
        if args.task == "detection":
            task_result = _run_detection(
                args, config, registry, device, run_dir, save_failures,
                model_name=model_name, compute_map_50_95=args.map_50_95,
            )
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
        run_dirs.append(run_dir)

        print(f"\n{'='*60}")
        print(f"Run ID:  {run.run_id}")
        print(f"Output:  {run_dir}")
        print(f"Device:  {device}")
        for name, path in artifacts.items():
            print(f"  {name}: {path}")

        if task_result and not task_result.skipped:
            print(f"\nMetrics ({args.task}" + (f" / {model_name}" if model_name else "") + "):")
            for k, v in task_result.metrics.items():
                if isinstance(v, (int, float)):
                    print(f"  {k}: {v}")
            # Collect for recommendation
            m_summary = {"model_name": model_name or "default"}
            for key in ("map_50", "recall", "precision", "false_positives_per_image"):
                if key in task_result.metrics and isinstance(task_result.metrics[key], (int, float)):
                    m_summary[key] = task_result.metrics[key]
            lat = task_result.metrics.get("inference_latency", {})
            if "p95_ms" in lat:
                m_summary["p95_latency_ms"] = lat["p95_ms"]
            model_metric_summaries.append(m_summary)
        elif task_result and task_result.skipped:
            print(f"\n[SKIPPED] {task_result.skip_reason}")

    # Auto-comparison
    if args.compare and len(run_dirs) >= 2:
        _run_comparison(config, run_dirs, model_metric_summaries, args.task)

    return 0


def _run_detection(
    args, config, registry, device, run_dir, save_failures,
    model_name=None, compute_map_50_95=False,
):
    from backend.app.evaluation.runners.detection_benchmark_runner import DetectionBenchmarkRunner
    from backend.app.evaluation.datasets.coco_yolo_loader import CocoYoloLoader

    dataset_name = args.dataset or config.get("evaluation", {}).get("default_detection_dataset", "weapon_eval")
    effective_model = model_name or "weapon_yolo"

    # Try to resolve real model adapter
    predict_fn = _make_predict_fn(config, effective_model, device)

    try:
        dataset_entry = registry.get_required(dataset_name)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        from backend.app.evaluation.schemas import BenchmarkTaskResult
        return BenchmarkTaskResult(
            task="detection", model_name=effective_model, dataset_name=dataset_name,
            skipped=True, skip_reason=str(exc),
        )

    class_names = config.get("datasets", {}).get(dataset_name, {}).get("class_names", ["weapon", "phone", "person"])
    loader = CocoYoloLoader(dataset_entry.path, class_names=class_names)
    samples = loader.load_yolo_annotations()

    if not samples:
        from backend.app.evaluation.schemas import BenchmarkTaskResult
        return BenchmarkTaskResult(
            task="detection", model_name=effective_model, dataset_name=dataset_name,
            skipped=True, skip_reason="No samples loaded from dataset path",
        )

    model_path = _resolve_model_path(config, effective_model)
    sweep_cfg = config.get("detection_threshold_sweep", {})

    runner = DetectionBenchmarkRunner(
        model_name=effective_model,
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
        compute_map_50_95=compute_map_50_95,
        threshold_sweep_config=sweep_cfg,
    )


def _make_predict_fn(config: dict, model_name: str, device: str):
    """
    Try to load a real YOLO adapter. Falls back to empty-predictions stub
    if weights are missing (optional model) or ultralytics is not installed.
    Required models raise and abort the run.
    """
    # Check model_candidates first, then legacy models section
    model_cfg = _find_model_cfg(config, model_name)

    if model_cfg:
        required = model_cfg.get("required", True)
        try:
            from backend.app.evaluation.model_resolver import resolve_adapter
            adapter = resolve_adapter(model_cfg, device=device, allow_missing=not required)
            if adapter is not None:
                logger.info("Loaded real inference adapter for '%s'", model_name)
                # Warmup
                n_warmup = config.get("inference", {}).get("warmup_runs", 5)
                adapter.warmup(n=n_warmup)

                def predict_fn(image_path: str) -> list[dict]:
                    pred = adapter.predict(image_path, confidence_threshold=0.25)
                    return [
                        {"bbox": d.bbox, "score": d.score, "class_id": d.class_id}
                        for d in pred.detections
                    ]
                return predict_fn
        except FileNotFoundError as exc:
            logger.error("Required model '%s' missing weights — aborting: %s", model_name, exc)
            raise
        except ImportError as exc:
            logger.warning("ultralytics not installed — using empty stub for '%s': %s", model_name, exc)
        except Exception as exc:
            logger.warning("Could not load model '%s': %s — using empty stub", model_name, exc)

    # Stub — no real model available
    logger.info("Using empty predict stub for '%s' (no real weights available)", model_name)

    def predict_fn_stub(image_path: str) -> list[dict]:
        return []

    return predict_fn_stub


def _find_model_cfg(config: dict, model_name: str) -> dict | None:
    """Find model config dict from model_candidates or legacy models section."""
    for task_candidates in config.get("model_candidates", {}).values():
        for cfg in task_candidates:
            if cfg.get("name") == model_name:
                return cfg
    # Legacy models section
    legacy = config.get("models", {}).get(model_name)
    if legacy:
        return {"name": model_name, "backend": legacy.get("backend", "ultralytics_yolo"),
                "path": legacy.get("path", ""), "required": False,
                "classes": legacy.get("class_names", [])}
    return None


def _resolve_model_path(config: dict, model_name: str) -> str:
    cfg = _find_model_cfg(config, model_name)
    return cfg.get("path", "") if cfg else ""


def _run_comparison(config: dict, run_dirs: list[Path], model_summaries: list[dict], task: str) -> None:
    from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
    policy = config.get("model_selection_policy", {})
    comparator = BenchmarkComparator(regression_policy=config.get("regression_policy", {}))

    print(f"\n{'='*60}")
    print("Model Comparison")

    # Pairwise comparisons (baseline = first, candidates = rest)
    baseline_dir = run_dirs[0]
    for cand_dir in run_dirs[1:]:
        try:
            comparison = comparator.compare(baseline_dir, cand_dir)
            out_path = cand_dir.parent / f"compare_{baseline_dir.name}_vs_{cand_dir.name}.md"
            comparator.write_report(comparison, out_path)
            print(f"Comparison: {out_path}")
            print(f"  Status: {comparison.overall_status.upper()}")
        except Exception as exc:
            logger.warning("Comparison failed: %s", exc)

    # Recommendation engine
    if model_summaries and policy:
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        rec = apply_model_selection_policy(model_summaries, policy, task=task)
        print(f"\nModel Selection Recommendation ({task}):")
        print(f"  Recommended: {rec.get('recommended_model') or 'none (policy failures)'}")
        print(f"  Reason: {rec.get('reason', '')}")
        print(f"  Confidence: {rec.get('confidence', 'unknown')}")


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
        return FaceBenchmarkRunner(device=device).run(
            pair_results=[], dataset_name=args.dataset or "face_eval", run_dir=run_dir,
        )
    if task == "reid":
        from backend.app.evaluation.runners.identity_benchmark_runner import ReIDBenchmarkRunner
        return ReIDBenchmarkRunner(device=device).run(
            query_embeddings=[], gallery_embeddings=[], dataset_name=args.dataset or "reid_eval", run_dir=run_dir,
        )
    if task == "identity_fusion":
        from backend.app.evaluation.runners.identity_benchmark_runner import IdentityFusionBenchmarkRunner
        return IdentityFusionBenchmarkRunner().run(
            scenario_results={}, merge_events=None, dataset_name=args.dataset or "identity_fusion",
        )
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
        return []

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
