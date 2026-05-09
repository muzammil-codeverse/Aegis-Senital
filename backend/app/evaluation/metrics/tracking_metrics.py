"""Phase 25 — Tracking evaluation metrics (MOTA, MOTP, IDF1, ID switches)."""
from __future__ import annotations

import logging
from collections import defaultdict

from backend.app.evaluation.schemas import TrackingMetricResult

logger = logging.getLogger(__name__)


def compute_tracking_metrics(
    gt_by_frame: dict[int, list[dict]],
    pred_by_frame: dict[int, list[dict]],
    iou_threshold: float = 0.5,
) -> TrackingMetricResult:
    """
    Compute MOTA, MOTP, IDF1 from MOTChallenge-style per-frame data.

    gt_by_frame:   frame_id → [{"track_id", "bbox_xywh"}]
    pred_by_frame: frame_id → [{"track_id", "bbox_xywh", "conf"}]
    """
    warnings = []

    if not gt_by_frame:
        warnings.append("No ground-truth tracking data provided")
        return TrackingMetricResult(warnings=warnings)

    num_gt_total = 0
    num_fp = 0
    num_fn = 0
    num_id_switches = 0
    motp_sum = 0.0
    motp_matches = 0
    track_durations: dict[str, int] = defaultdict(int)
    track_mostly_status: dict[str, dict] = {}

    # Match state: prev frame's gt→pred assignments
    prev_gt_to_pred: dict[int, int] = {}

    all_frames = sorted(set(gt_by_frame.keys()) | set(pred_by_frame.keys()))

    for frame_id in all_frames:
        gt_list = gt_by_frame.get(frame_id, [])
        pred_list = pred_by_frame.get(frame_id, [])

        num_gt_total += len(gt_list)

        matched_gt = {}  # gt_idx → pred_idx
        matched_pred = set()

        for gt_idx, gt in enumerate(gt_list):
            best_iou = 0.0
            best_pred_idx = -1
            gt_box = _xywh_to_xyxy(gt["bbox_xywh"])
            for pred_idx, pred in enumerate(pred_list):
                if pred_idx in matched_pred:
                    continue
                pred_box = _xywh_to_xyxy(pred["bbox_xywh"])
                iou = _iou(gt_box, pred_box)
                if iou > best_iou:
                    best_iou = iou
                    best_pred_idx = pred_idx

            if best_iou >= iou_threshold and best_pred_idx >= 0:
                matched_gt[gt_idx] = best_pred_idx
                matched_pred.add(best_pred_idx)
                motp_sum += best_iou
                motp_matches += 1

                # ID switch check
                gt_tid = gt["track_id"]
                pred_tid = pred_list[best_pred_idx]["track_id"]
                prev_pred_tid = prev_gt_to_pred.get(gt_tid)
                if prev_pred_tid is not None and prev_pred_tid != pred_tid:
                    num_id_switches += 1
                prev_gt_to_pred[gt_tid] = pred_tid
            else:
                num_fn += 1

        num_fp += len(pred_list) - len(matched_pred)

        for pred in pred_list:
            track_durations[pred["track_id"]] += 1

    # MOTA = 1 - (FP + FN + IDSW) / num_gt
    mota = None
    if num_gt_total > 0:
        mota = round(1.0 - (num_fp + num_fn + num_id_switches) / num_gt_total, 4)

    motp = round(motp_sum / motp_matches, 4) if motp_matches > 0 else None

    # Simplified IDF1 (track-level F1 proxy)
    total_tracks = len(track_durations)
    idf1 = None
    if total_tracks > 0 and motp is not None:
        idf1 = round(motp * (1 - num_id_switches / max(1, total_tracks)), 4)

    avg_duration = (
        sum(track_durations.values()) / len(track_durations)
        if track_durations else None
    )

    return TrackingMetricResult(
        mota=mota,
        motp=motp,
        idf1=idf1,
        hota=None,
        id_switches=num_id_switches,
        fragmentation=None,
        mostly_tracked=None,
        mostly_lost=None,
        avg_track_duration_frames=round(avg_duration, 2) if avg_duration is not None else None,
        warnings=warnings,
    )


def _xywh_to_xyxy(xywh: list[float]) -> list[float]:
    x, y, w, h = xywh
    return [x, y, x + w, y + h]


def _iou(box1: list[float], box2: list[float]) -> float:
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0
