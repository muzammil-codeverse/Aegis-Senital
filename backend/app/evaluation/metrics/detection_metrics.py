"""Phase 25/26 — Detection evaluation metrics (mAP@0.5, mAP@0.5:0.95, threshold sweep)."""
from __future__ import annotations

import logging
from typing import Any

from backend.app.evaluation.schemas import DetectionMetricResult

logger = logging.getLogger(__name__)

_MAP_50_95_THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]


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
    """Compute area under the precision-recall curve using 11-point interpolation."""
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

    predictions: [{"bbox": [x1,y1,x2,y2], "score": float, "class_id": int}]
    ground_truth: [{"bbox" or "bbox_xyxy": [x1,y1,x2,y2], "class_id": int}]
    Returns (tp_flags for predictions sorted by score desc, gt_matched flags).
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
            if len(gt_box) < 4 or len(pred_box) < 4:
                continue
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


def _compute_class_ap(
    all_tp: list[bool],
    all_scores: list[float],
    n_gt: int,
) -> tuple[float, list[float], list[float]]:
    """Compute AP, precision list, recall list for one class."""
    if n_gt == 0 and not all_tp:
        return 0.0, [], []
    sorted_pairs = sorted(zip(all_scores, all_tp), key=lambda x: x[0], reverse=True)
    cum_tp = 0
    precisions, recalls = [], []
    for i, (_, tp) in enumerate(sorted_pairs):
        cum_tp += int(tp)
        precisions.append(cum_tp / (i + 1))
        recalls.append(cum_tp / n_gt if n_gt > 0 else 0.0)
    return compute_ap(precisions, recalls), precisions, recalls


def _gather_class_stats(
    samples: list[dict],
    predictions_by_sample: dict[str, list[dict]],
    num_classes: int,
    iou_threshold: float,
    confidence_threshold: float = 0.0,
) -> tuple[dict, dict, dict, int, int, list[float]]:
    """Gather TP/FP arrays and GT counts for all classes at given IoU and confidence thresholds."""
    all_tp: dict[int, list[bool]] = {i: [] for i in range(num_classes)}
    all_scores: dict[int, list[float]] = {i: [] for i in range(num_classes)}
    num_gt: dict[int, int] = {i: 0 for i in range(num_classes)}
    total_fp = 0
    total_fn = 0
    iou_values: list[float] = []

    for sample in samples:
        sample_id = sample.get("sample_id", "")
        gt_anns = sample.get("annotations", [])
        preds_raw = predictions_by_sample.get(sample_id, [])
        preds = [p for p in preds_raw if p.get("score", 0.0) >= confidence_threshold]

        for ann in gt_anns:
            cls_id = ann.get("class_id", 0)
            if 0 <= cls_id < num_classes:
                num_gt[cls_id] += 1

        tp_flags, gt_matched = match_predictions(preds, gt_anns, iou_threshold=iou_threshold)

        for pred, tp in zip(
            sorted(preds, key=lambda p: p.get("score", 0.0), reverse=True),
            tp_flags,
        ):
            cls_id = pred.get("class_id", 0)
            if 0 <= cls_id < num_classes:
                all_tp[cls_id].append(tp)
                all_scores[cls_id].append(pred.get("score", 0.0))

        total_fp += sum(1 for t in tp_flags if not t)
        total_fn += sum(1 for m in gt_matched if not m)

        for pred, tp in zip(
            sorted(preds, key=lambda p: p.get("score", 0.0), reverse=True),
            tp_flags,
        ):
            if tp:
                gt_idx = _find_matched_gt(pred, gt_anns)
                if gt_idx >= 0:
                    gt_box = gt_anns[gt_idx].get("bbox") or gt_anns[gt_idx].get("bbox_xyxy") or []
                    if len(gt_box) >= 4:
                        iou = compute_iou(pred["bbox"], gt_box)
                        iou_values.append(iou)

    return all_tp, all_scores, num_gt, total_fp, total_fn, iou_values


def compute_detection_metrics(
    samples: list[dict],
    predictions_by_sample: dict[str, list[dict]],
    class_names: list[str],
    iou_thresholds: list[float] | None = None,
    compute_map_50_95: bool = False,
) -> DetectionMetricResult:
    """
    Compute mAP@0.5, precision, recall, F1, per-class AP.
    When compute_map_50_95=True also computes mAP@0.5:0.95 and per-class AP@0.5:0.95.

    samples: [{ sample_id, annotations: [{class_id, bbox_xyxy}] }]
    predictions_by_sample: sample_id → [{"bbox", "score", "class_id"}]
    """
    warnings: list[str] = []
    if not samples:
        warnings.append("No samples provided for detection evaluation")
        return DetectionMetricResult(warnings=warnings)

    num_classes = len(class_names)
    all_tp, all_scores, num_gt, total_fp, total_fn, iou_values = _gather_class_stats(
        samples, predictions_by_sample, num_classes, iou_threshold=0.5
    )

    per_class_ap: dict[str, float] = {}
    per_class_metrics: dict[str, dict] = {}

    for cls_id in range(num_classes):
        tps = all_tp[cls_id]
        scores = all_scores[cls_id]
        n_gt = num_gt[cls_id]
        if n_gt == 0 and not tps:
            continue

        ap_50, precisions, recalls = _compute_class_ap(tps, scores, n_gt)
        cls_name = class_names[cls_id] if cls_id < len(class_names) else str(cls_id)
        per_class_ap[cls_name] = round(ap_50, 4)

        # Per-class aggregated precision/recall/F1
        cls_tp_count = sum(tps)
        cls_det_count = len(tps)
        cls_prec = cls_tp_count / cls_det_count if cls_det_count > 0 else None
        cls_rec = cls_tp_count / n_gt if n_gt > 0 else None
        cls_f1 = (
            2 * cls_prec * cls_rec / (cls_prec + cls_rec)
            if cls_prec and cls_rec and (cls_prec + cls_rec) > 0
            else None
        )
        per_class_metrics[cls_name] = {
            "ap_50": round(ap_50, 4),
            "ap_50_95": None,  # filled below if requested
            "precision": round(cls_prec, 4) if cls_prec is not None else None,
            "recall": round(cls_rec, 4) if cls_rec is not None else None,
            "f1": round(cls_f1, 4) if cls_f1 is not None else None,
            "num_gt": n_gt,
            "num_detections": cls_det_count,
        }

    # mAP@0.5:0.95
    map_50_95_val: float | None = None
    if compute_map_50_95:
        class_ap_over_thresholds: dict[int, list[float]] = {i: [] for i in range(num_classes)}
        for iou_t in _MAP_50_95_THRESHOLDS:
            tp_t, sc_t, ng_t, _, _, _ = _gather_class_stats(
                samples, predictions_by_sample, num_classes, iou_threshold=iou_t
            )
            for cls_id in range(num_classes):
                if ng_t[cls_id] == 0 and not tp_t[cls_id]:
                    continue
                ap_t, _, _ = _compute_class_ap(tp_t[cls_id], sc_t[cls_id], ng_t[cls_id])
                class_ap_over_thresholds[cls_id].append(ap_t)

        # Average per-class AP across thresholds, then across classes
        class_ap_50_95: list[float] = []
        for cls_id, ap_list in class_ap_over_thresholds.items():
            if ap_list:
                avg = sum(ap_list) / len(ap_list)
                class_ap_50_95.append(avg)
                cls_name = class_names[cls_id] if cls_id < len(class_names) else str(cls_id)
                if cls_name in per_class_metrics:
                    per_class_metrics[cls_name]["ap_50_95"] = round(avg, 4)

        map_50_95_val = round(sum(class_ap_50_95) / len(class_ap_50_95), 4) if class_ap_50_95 else None

    # Global precision / recall / F1
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

    iou_dist: dict = {}
    if iou_values:
        iou_dist = {
            "mean": round(sum(iou_values) / len(iou_values), 4),
            "min": round(min(iou_values), 4),
            "max": round(max(iou_values), 4),
        }

    return DetectionMetricResult(
        map_50=round(map_50, 4) if map_50 is not None else None,
        map_50_95=map_50_95_val,
        precision=round(precision, 4) if precision is not None else None,
        recall=round(recall, 4) if recall is not None else None,
        f1=round(f1, 4) if f1 is not None else None,
        per_class_ap=per_class_ap,
        per_class_metrics=per_class_metrics,
        false_positives_per_image=round(fps_per_image, 4) if fps_per_image is not None else None,
        false_negatives_per_image=round(fns_per_image, 4) if fns_per_image is not None else None,
        iou_distribution=iou_dist,
        class_names=class_names,
        warnings=warnings,
    )


def compute_threshold_sweep(
    samples: list[dict],
    predictions_by_sample: dict[str, list[dict]],
    class_names: list[str],
    model_name: str = "",
    thresholds: list[float] | None = None,
) -> list[dict]:
    """
    Compute detection metrics at multiple confidence thresholds.

    Returns a list of row dicts (one per class per threshold) suitable for CSV export.
    Columns: model_name, class, threshold, precision, recall, f1, fp_per_image,
             fn_per_image, map_50, map_50_95 (None — omitted for speed).
    """
    if thresholds is None:
        thresholds = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70]

    rows: list[dict] = []
    num_classes = len(class_names)
    n_samples = len(samples)

    for ct in thresholds:
        all_tp, all_scores, num_gt, total_fp, total_fn, _ = _gather_class_stats(
            samples, predictions_by_sample, num_classes,
            iou_threshold=0.5, confidence_threshold=ct,
        )
        # Global row
        total_det = sum(len(v) for v in all_tp.values())
        total_tp_count = sum(sum(v) for v in all_tp.values())
        total_gt_count = sum(num_gt.values())
        g_prec = total_tp_count / total_det if total_det > 0 else 0.0
        g_rec = total_tp_count / total_gt_count if total_gt_count > 0 else 0.0
        g_f1 = (
            2 * g_prec * g_rec / (g_prec + g_rec)
            if (g_prec + g_rec) > 0 else 0.0
        )
        rows.append({
            "model_name": model_name,
            "class": "all",
            "threshold": ct,
            "precision": round(g_prec, 4),
            "recall": round(g_rec, 4),
            "f1": round(g_f1, 4),
            "fp_per_image": round(total_fp / n_samples, 4) if n_samples > 0 else 0.0,
            "fn_per_image": round(total_fn / n_samples, 4) if n_samples > 0 else 0.0,
            "map_50": None,
            "map_50_95": None,
        })
        # Per-class rows
        for cls_id in range(num_classes):
            cls_name = class_names[cls_id]
            tps = all_tp[cls_id]
            scores = all_scores[cls_id]
            n_gt = num_gt[cls_id]
            ap_50, _, _ = _compute_class_ap(tps, scores, n_gt)
            tp_c = sum(tps)
            det_c = len(tps)
            c_prec = tp_c / det_c if det_c > 0 else 0.0
            c_rec = tp_c / n_gt if n_gt > 0 else 0.0
            c_f1 = 2 * c_prec * c_rec / (c_prec + c_rec) if (c_prec + c_rec) > 0 else 0.0
            rows.append({
                "model_name": model_name,
                "class": cls_name,
                "threshold": ct,
                "precision": round(c_prec, 4),
                "recall": round(c_rec, 4),
                "f1": round(c_f1, 4),
                "fp_per_image": round(total_fp / n_samples, 4) if n_samples > 0 else 0.0,
                "fn_per_image": round(total_fn / n_samples, 4) if n_samples > 0 else 0.0,
                "map_50": round(ap_50, 4),
                "map_50_95": None,
            })

    return rows


def _find_matched_gt(pred: dict, gt_anns: list[dict]) -> int:
    pred_box = pred.get("bbox", [])
    pred_cls = pred.get("class_id", -1)
    best_iou = 0.0
    best_idx = -1
    for i, gt in enumerate(gt_anns):
        if gt.get("class_id", -1) != pred_cls:
            continue
        gt_box = gt.get("bbox") or gt.get("bbox_xyxy") or []
        if len(gt_box) < 4 or len(pred_box) < 4:
            continue
        iou = compute_iou(pred_box, gt_box)
        if iou > best_iou:
            best_iou = iou
            best_idx = i
    return best_idx if best_iou >= 0.5 else -1
