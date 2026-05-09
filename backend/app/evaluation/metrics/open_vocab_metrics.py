"""Phase 25 — Open-vocab prompt evaluation metrics (precision, recall, F1 per prompt)."""
from __future__ import annotations

import logging
import time

from backend.app.evaluation.schemas import OpenVocabMetricResult, OpenVocabPromptMetricResult

logger = logging.getLogger(__name__)


def compute_open_vocab_metrics(
    samples_by_prompt: dict[str, list[dict]],
    predict_fn,
    prompt_configs: list[dict],
) -> OpenVocabMetricResult:
    """
    Evaluate each prompt independently.

    samples_by_prompt: { prompt_id: [{"image_path", "has_detection": bool, "bbox": list|null}] }
    predict_fn: callable(image_path, prompt_text, threshold) → [{"label", "score", "bbox"}]
    prompt_configs: [{"prompt_id", "text", "threshold"}]
    """
    warnings = []
    prompt_results = []
    total_latencies = []

    prompt_by_id = {p["prompt_id"]: p for p in prompt_configs}

    for prompt_id, samples in samples_by_prompt.items():
        if not samples:
            continue
        p_cfg = prompt_by_id.get(prompt_id, {})
        prompt_text = p_cfg.get("text", prompt_id)
        threshold = p_cfg.get("threshold", 0.35)

        tp = fp = fn = 0
        latencies = []
        scores = []
        iou_values = []
        fp_categories = []

        for sample in samples:
            image_path = sample.get("image_path", "")
            has_gt = bool(sample.get("has_detection"))
            gt_bbox = sample.get("bbox")

            try:
                t0 = time.time()
                predictions = predict_fn(image_path, prompt_text, threshold)
                latency_ms = (time.time() - t0) * 1000
                latencies.append(latency_ms)
            except Exception as exc:
                logger.warning("Open-vocab predict_fn failed for %s: %s", image_path, exc)
                warnings.append(f"Prediction failed for {image_path}: {exc}")
                continue

            has_pred = bool(predictions)
            for pred in predictions:
                scores.append(pred.get("score", 0.0))
                if gt_bbox and pred.get("bbox"):
                    from backend.app.evaluation.metrics.detection_metrics import compute_iou
                    iou_values.append(compute_iou(pred["bbox"], gt_bbox))

            if has_gt and has_pred:
                tp += 1
            elif has_gt and not has_pred:
                fn += 1
            elif not has_gt and has_pred:
                fp += 1
                for pred in predictions:
                    fp_categories.append(pred.get("label", "unknown"))

        precision = tp / (tp + fp) if (tp + fp) > 0 else None
        recall = tp / (tp + fn) if (tp + fn) > 0 else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and (precision + recall) > 0
            else None
        )
        avg_iou = sum(iou_values) / len(iou_values) if iou_values else None
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        total_latencies.extend(latencies)

        score_dist = {}
        if scores:
            score_dist = {
                "mean": round(sum(scores) / len(scores), 4),
                "min": round(min(scores), 4),
                "max": round(max(scores), 4),
            }

        prompt_results.append(OpenVocabPromptMetricResult(
            prompt_id=prompt_id,
            prompt_text=prompt_text,
            threshold=threshold,
            precision=round(precision, 4) if precision is not None else None,
            recall=round(recall, 4) if recall is not None else None,
            f1=round(f1, 4) if f1 is not None else None,
            avg_iou=round(avg_iou, 4) if avg_iou is not None else None,
            avg_latency_ms=round(avg_latency, 2) if avg_latency is not None else None,
            detections_count=tp + fp,
            score_distribution=score_dist,
            false_positive_categories=list(set(fp_categories)),
        ))

    total_images = sum(len(s) for s in samples_by_prompt.values())
    avg_latency_per_image = (
        sum(total_latencies) / len(total_latencies) if total_latencies else None
    )

    return OpenVocabMetricResult(
        prompt_results=prompt_results,
        avg_latency_per_image_ms=round(avg_latency_per_image, 2) if avg_latency_per_image is not None else None,
        total_images=total_images,
        warnings=warnings,
    )
