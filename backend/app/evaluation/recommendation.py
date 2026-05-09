"""Phase 26B — Evidence-based detector recommendation helpers."""
from __future__ import annotations


def recommend_detection_model(
    task_key: str,
    model_metrics: list[dict],
    *,
    sample_size: int = 0,
) -> dict:
    if not model_metrics:
        return {
            "recommended_model": None,
            "reason": "No real benchmark data available",
            "confidence": "low",
        }

    normalized_task = task_key.lower()
    if normalized_task == "weapon":
        ordered = sorted(
            model_metrics,
            key=lambda item: (
                -(item.get("recall") or 0.0),
                item.get("false_negatives_per_image") if item.get("false_negatives_per_image") is not None else float("inf"),
                -(item.get("map_50") or 0.0),
                item.get("p95_latency_ms") if item.get("p95_latency_ms") is not None else float("inf"),
                item.get("false_positives_per_image") if item.get("false_positives_per_image") is not None else float("inf"),
                item.get("peak_gpu_mb") if item.get("peak_gpu_mb") is not None else float("inf"),
            ),
        )
    else:
        ordered = sorted(
            model_metrics,
            key=lambda item: (
                -(item.get("precision") or 0.0),
                -(item.get("recall") or 0.0),
                item.get("false_positives_per_image") if item.get("false_positives_per_image") is not None else float("inf"),
                -(item.get("map_50") or 0.0),
                item.get("p95_latency_ms") if item.get("p95_latency_ms") is not None else float("inf"),
                item.get("peak_gpu_mb") if item.get("peak_gpu_mb") is not None else float("inf"),
            ),
        )

    best = ordered[0]
    evaluated_models = len([item for item in model_metrics if item.get("real_run")])
    if sample_size > 0 and evaluated_models > 1:
        confidence = "high"
    elif sample_size > 0:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "recommended_model": best.get("model_name"),
        "reason": (
            f"precision={best.get('precision')} recall={best.get('recall')} "
            f"mAP@0.5={best.get('map_50')} p95={best.get('p95_latency_ms')}ms"
        ),
        "confidence": confidence,
        "ranked_models": [item.get("model_name") for item in ordered],
    }
