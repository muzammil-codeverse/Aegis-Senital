"""Phase 25 — Detection evaluation metrics (mAP, precision, recall, F1, confusion matrix)."""
from __future__ import annotations

import logging
from typing import Any

from backend.app.evaluation.schemas import DetectionMetricResult

logger = logging.getLogger(__name__)


def compute_iou(box1: list[float], box2: list[float]) -> float:
    """Compute IoU between two [x1,y1,x2,y2] boxes."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def compute_ap(precisions: list[float], recalls: list[float]) -> float:
    """Compute area under precision-recall curve using 11-point interpolation."""
    if not precisions or not recalls:
        return 0.0
    ap = 0.0
    for t in [r / 10.0 for r in range(11)]:
        p_at_r = [p for p, r in zip(precisions, recalls) if r >= t]
        ap += max(p_at_r) if p_at_r else 0.0
    return ap / 11.0


def match_predictions(
    predictions: list[dict],
    ground_truth: list[dict],
    iou_threshold: float = 0.5,
) -> tuple[list[bool], list[bool]]:
    """
    Match predictions to ground truth boxes.
    Returns (tp_flags for predictions, gt_matched flags).
    predictions: [{"bbox": [x1,y1,x2,y2], "score": float, "class_id": int}]
    ground_truth: [{"bbox": [x1,y1,x2,y2], "class_id": int}]
    """
    gt_matched = [False] * len(ground_truth)
    tp_flags = []

    preds_sorted = sorted(predictions, key=lambda p: p.get("score", 0.0), reverse=True)

    for pred in preds_sorted:
        pred_box = pred.get("bbox", [])
        pred_class = pred.get("class_id", -1)
        best_iou = 0.0
        best_gt_idx = -1

        for gt_idx, gt in enumerate(ground_truth):
            if gt_matched[gt_idx]:
                continue
            if gt.get("class_id", -1) != pred_class:
                continue
            gt_box = gt.get("bbox") or gt.get("bbox_xyxy") or []
            iou = compute_iou(pred_box, gt_box)
            if iou > best_iou:
                best_iou = iou
                best_gt_idx = gt_idx

        if best_iou >= iou_threshold and best_gt_idx >= 0:
            tp_flags.append(True)
            gt_matched[best_gt_idx] = True
        else:
            tp_flags.append(False)

    return tp_flags, gt_matched


def compute_detection_metrics(
    samples: list[dict],
    predictions_by_sample: dict[str, list[dict]],
    class_names: list[str],
    iou_thresholds: list[float] | None = None,
) -> DetectionMetricResult:
    """
    Compute mAP, precision, recall, F1, per-class AP.

    samples: list of { sample_id, annotations: [{class_id, bbox_xyxy}] }
    predictions_by_sample: sample_id → [{"bbox", "score", "class_id"}]
    class_names: ordered list of class names
    """
    if iou_thresholds is None:
        iou_thresholds = [0.5]

    warnings = []
    if not samples:
        warnings.append("No samples provided for detection evaluation")
        return DetectionMetricResult(warnings=warnings)

    num_classes = len(class_names)
    all_tp: dict[int, list[bool]] = {i: [] for i in range(num_classes)}
    all_scores: dict[int, list[float]] = {i: [] for i in range(num_classes)}
    num_gt: dict[int, int] = {i: 0 for i in range(num_classes)}
    total_fp = 0
    total_fn = 0
    iou_values = []

    for sample in samples:
        sample_id = sample.get("sample_id", "")
        gt_anns = sample.get("annotations", [])
        preds = predictions_by_sample.get(sample_id, [])

        for ann in gt_anns:
            cls_id = ann.get("class_id", 0)
            if 0 <= cls_id < num_classes:
                num_gt[cls_id] += 1

        tp_flags, gt_matched = match_predictions(preds, gt_anns, iou_threshold=0.5)

        for pred, tp in zip(sorted(preds, key=lambda p: p.get("score", 0.0), reverse=True), tp_flags):
            cls_id = pred.get("class_id", 0)
            if 0 <= cls_id < num_classes:
                all_tp[cls_id].append(tp)
                all_scores[cls_id].append(pred.get("score", 0.0))

        total_fp += sum(1 for t in tp_flags if not t)
        total_fn += sum(1 for m in gt_matched if not m)

        for pred, tp in zip(sorted(preds, key=lambda p: p.get("score", 0.0), reverse=True), tp_flags):
            if tp:
                gt_idx = _find_matched_gt(pred, gt_anns)
                if gt_idx >= 0:
                    gt_box = gt_anns[gt_idx].get("bbox") or gt_anns[gt_idx].get("bbox_xyxy") or []
                    iou = compute_iou(pred["bbox"], gt_box)
                    iou_values.append(iou)

    per_class_ap = {}
    all_precisions = []
    all_recalls_flat = []

    for cls_id in range(num_classes):
        tps = all_tp[cls_id]
        scores = all_scores[cls_id]
        n_gt = num_gt[cls_id]
        if n_gt == 0 and not tps:
            continue

        sorted_pairs = sorted(zip(scores, tps), key=lambda x: x[0], reverse=True)
        cum_tp = 0
        precisions = []
        recalls = []
        for i, (_, tp) in enumerate(sorted_pairs):
            cum_tp += int(tp)
            p = cum_tp / (i + 1)
            r = cum_tp / n_gt if n_gt > 0 else 0.0
            precisions.append(p)
            recalls.append(r)

        ap = compute_ap(precisions, recalls)
        cls_name = class_names[cls_id] if cls_id < len(class_names) else str(cls_id)
        per_class_ap[cls_name] = round(ap, 4)
        all_precisions.extend(precisions)
        all_recalls_flat.extend(recalls)

    map_50 = sum(per_class_ap.values()) / len(per_class_ap) if per_class_ap else None
    total_det = sum(len(v) for v in all_tp.values())
    total_tp = sum(sum(v) for v in all_tp.values())
    precision = total_tp / total_det if total_det > 0 else None
    total_gt = sum(num_gt.values())
    recall = total_tp / total_gt if total_gt > 0 else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall and (precision + recall) > 0
        else None
    )
    fps_per_image = total_fp / len(samples) if samples else None
    fns_per_image = total_fn / len(samples) if samples else None

    iou_dist = {}
    if iou_values:
        iou_dist = {
            "mean": round(sum(iou_values) / len(iou_values), 4),
            "min": round(min(iou_values), 4),
            "max": round(max(iou_values), 4),
        }

    return DetectionMetricResult(
        map_50=round(map_50, 4) if map_50 is not None else None,
        map_50_95=None,  # requires multi-threshold loop (compute separately if needed)
        precision=round(precision, 4) if precision is not None else None,
        recall=round(recall, 4) if recall is not None else None,
        f1=round(f1, 4) if f1 is not None else None,
        per_class_ap=per_class_ap,
        false_positives_per_image=round(fps_per_image, 4) if fps_per_image is not None else None,
        false_negatives_per_image=round(fns_per_image, 4) if fns_per_image is not None else None,
        iou_distribution=iou_dist,
        class_names=class_names,
        warnings=warnings,
    )


def _find_matched_gt(pred: dict, gt_anns: list[dict]) -> int:
    pred_box = pred.get("bbox", [])
    pred_cls = pred.get("class_id", -1)
    best_iou = 0.0
    best_idx = -1
    for i, gt in enumerate(gt_anns):
        if gt.get("class_id", -1) != pred_cls:
            continue
        gt_box = gt.get("bbox") or gt.get("bbox_xyxy") or []
        iou = compute_iou(pred_box, gt_box)
        if iou > best_iou:
            best_iou = iou
            best_idx = i
    return best_idx if best_iou >= 0.5 else -1
