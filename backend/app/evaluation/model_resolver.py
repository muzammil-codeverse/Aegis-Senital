"""Phase 26 — Model resolver: load detection adapters from evaluation config."""
from __future__ import annotations

import logging
from typing import Iterator

from backend.app.evaluation.inference.base import DetectionModelAdapter

logger = logging.getLogger(__name__)

_SUPPORTED_BACKENDS = frozenset({"ultralytics_yolo", "open_vocab_adapter"})


def resolve_adapter(
    model_cfg: dict,
    device: str = "cpu",
    *,
    allow_missing: bool = False,
) -> DetectionModelAdapter | None:
    """
    Resolve a model config dict to a loaded DetectionModelAdapter.

    Returns None (with a warning) if the model is optional and its weights are missing.
    Raises FileNotFoundError if the model is required and weights are missing.
    Raises ImportError if the backend library is not installed.
    Never downloads model weights silently.
    """
    name = model_cfg.get("name", "unknown")
    backend = model_cfg.get("backend", "ultralytics_yolo")
    path = str(model_cfg.get("path", ""))
    required = model_cfg.get("required", True)
    class_names = model_cfg.get("classes", [])
    version = model_cfg.get("version")
    image_size = int(model_cfg.get("image_size", 640))

    if backend not in _SUPPORTED_BACKENDS:
        raise ValueError(f"Unsupported model backend '{backend}' for model '{name}'")

    if backend == "ultralytics_yolo":
        from backend.app.evaluation.inference.yolo_inference_adapter import YOLOInferenceAdapter
        adapter: DetectionModelAdapter = YOLOInferenceAdapter(
            model_path=path,
            name=name,
            device=device,
            class_names=class_names,
            version=version,
            image_size=image_size,
        )
        try:
            adapter.load()
        except FileNotFoundError as exc:
            if required and not allow_missing:
                raise
            logger.warning("Optional YOLO model '%s' skipped — weights missing: %s", name, exc)
            return None
        except ImportError:
            if required and not allow_missing:
                raise
            logger.warning("Optional YOLO model '%s' skipped — ultralytics not installed", name)
            return None
        return adapter

    if backend == "open_vocab_adapter":
        from backend.app.evaluation.inference.open_vocab_inference_adapter import OpenVocabInferenceAdapter
        adapter = OpenVocabInferenceAdapter(
            name=name,
            device=device,
            prompt_text=model_cfg.get("prompt_text", "weapon"),
            threshold=float(model_cfg.get("threshold", 0.35)),
            config=model_cfg.get("config", {}),
        )
        adapter.load()
        if not adapter.is_loaded():
            if required:
                raise RuntimeError(f"Required open-vocab adapter '{name}' failed to load")
            logger.warning("Optional open-vocab adapter '%s' unavailable", name)
            return None
        return adapter

    return None  # unreachable — validated above


def resolve_candidates(
    config: dict,
    task: str,
    device: str = "cpu",
) -> Iterator[tuple[dict, DetectionModelAdapter | None]]:
    """
    Yield (model_cfg, adapter_or_None) for each candidate in config[model_candidates][task].

    Required candidates with missing weights raise immediately.
    Optional candidates with missing weights yield (cfg, None) with a warning.
    """
    candidates = config.get("model_candidates", {}).get(task, [])
    if not candidates:
        logger.warning("No model_candidates configured for task '%s'", task)
        return

    for model_cfg in candidates:
        name = model_cfg.get("name", "?")
        required = model_cfg.get("required", True)
        try:
            adapter = resolve_adapter(model_cfg, device=device, allow_missing=not required)
            yield model_cfg, adapter
        except FileNotFoundError as exc:
            if required:
                raise
            logger.warning("Skipping optional candidate '%s': %s", name, exc)
            yield model_cfg, None
        except Exception as exc:
            if required:
                raise
            logger.error("Failed to resolve optional model '%s': %s", name, exc)
            yield model_cfg, None


def apply_model_selection_policy(
    model_metrics: list[dict],
    policy: dict,
    task: str = "detection",
) -> dict:
    """
    Apply model_selection_policy to a list of model result dicts.
    Returns a recommendation dict with model_name, reason, and confidence.

    model_metrics: [{"model_name": str, "map_50": float, "recall": float,
                      "false_positives_per_image": float, "p95_latency_ms": float,
                      "peak_gpu_mb": float}]
    """
    min_map = float(policy.get("min_map_50", 0.70))
    min_recall = float(policy.get("min_recall", 0.65))
    max_fp = float(policy.get("max_fp_per_image", 0.25))
    max_p95_ms = float(policy.get("max_p95_latency_ms", 50))
    max_gpu_mb = float(policy.get("max_gpu_memory_mb", 3000))
    prefer_recall = bool(policy.get(f"prefer_recall_for_{task}", False))

    eligible = []
    reasons_by_model: dict[str, list[str]] = {}

    for m in model_metrics:
        name = m.get("model_name", "?")
        issues = []
        if m.get("map_50") is not None and m["map_50"] < min_map:
            issues.append(f"mAP@0.5 {m['map_50']:.3f} < policy minimum {min_map}")
        if m.get("recall") is not None and m["recall"] < min_recall:
            issues.append(f"recall {m['recall']:.3f} < policy minimum {min_recall}")
        if m.get("false_positives_per_image") is not None and m["false_positives_per_image"] > max_fp:
            issues.append(f"FP/image {m['false_positives_per_image']:.3f} > max {max_fp}")
        if m.get("p95_latency_ms") is not None and m["p95_latency_ms"] > max_p95_ms:
            issues.append(f"p95 latency {m['p95_latency_ms']:.1f}ms > max {max_p95_ms}ms")
        if m.get("peak_gpu_mb") is not None and m["peak_gpu_mb"] > max_gpu_mb:
            issues.append(f"GPU memory {m['peak_gpu_mb']:.0f}MB > max {max_gpu_mb}MB")
        reasons_by_model[name] = issues
        if not issues:
            eligible.append(m)

    if not eligible:
        return {
            "recommended_model": None,
            "reason": "No model passed all policy thresholds",
            "policy_failures": {m["model_name"]: reasons_by_model[m["model_name"]] for m in model_metrics},
            "confidence": "low",
        }

    # Sort eligible models: primary key = recall (if task prefers recall) or mAP@0.5
    def _score(m: dict) -> float:
        recall = m.get("recall") or 0.0
        map50 = m.get("map_50") or 0.0
        return recall if prefer_recall else map50

    best = max(eligible, key=_score)
    runner_up = [m for m in eligible if m["model_name"] != best["model_name"]]

    reason_parts = []
    if best.get("map_50") is not None:
        reason_parts.append(f"mAP@0.5={best['map_50']:.3f}")
    if best.get("recall") is not None:
        reason_parts.append(f"recall={best['recall']:.3f}")
    if best.get("p95_latency_ms") is not None:
        reason_parts.append(f"p95={best['p95_latency_ms']:.1f}ms")
    if best.get("false_positives_per_image") is not None:
        reason_parts.append(f"FP/img={best['false_positives_per_image']:.3f}")

    return {
        "recommended_model": best["model_name"],
        "reason": "; ".join(reason_parts) if reason_parts else "Best eligible model",
        "runner_up": runner_up[0]["model_name"] if runner_up else None,
        "policy_failures": {m["model_name"]: reasons_by_model[m["model_name"]] for m in model_metrics},
        "confidence": "high" if len(eligible) > 1 else "medium",
    }
