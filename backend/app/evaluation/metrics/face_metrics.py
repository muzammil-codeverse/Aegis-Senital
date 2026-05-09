"""Phase 25 — Face recognition evaluation metrics (FAR, FRR, TAR, ROC, threshold sweep)."""
from __future__ import annotations

import logging
from typing import Any

from backend.app.evaluation.schemas import FaceMetricResult

logger = logging.getLogger(__name__)


def compute_face_metrics(
    pair_results: list[dict],
    far_thresholds: list[float] | None = None,
) -> FaceMetricResult:
    """
    Compute face recognition metrics from pair similarity scores.

    pair_results: [{"same": bool, "similarity": float}]
    far_thresholds: list of FAR values at which to report TAR.
    """
    warnings = []
    if far_thresholds is None:
        far_thresholds = [1e-1, 1e-2, 1e-3, 1e-4]

    if not pair_results:
        warnings.append("No pair results for face evaluation")
        return FaceMetricResult(warnings=warnings)

    genuine_scores = [r["similarity"] for r in pair_results if r.get("same")]
    impostor_scores = [r["similarity"] for r in pair_results if not r.get("same")]

    if not genuine_scores or not impostor_scores:
        warnings.append("Insufficient genuine or impostor pairs for face evaluation")
        return FaceMetricResult(warnings=warnings)

    # Threshold sweep
    all_scores = sorted(set(genuine_scores + impostor_scores))
    threshold_sweep = []
    roc_curve = []

    best_threshold = 0.5
    best_f1 = 0.0

    for thresh in all_scores:
        tp = sum(1 for s in genuine_scores if s >= thresh)
        fn = len(genuine_scores) - tp
        fp = sum(1 for s in impostor_scores if s >= thresh)
        tn = len(impostor_scores) - fp

        far = fp / len(impostor_scores) if impostor_scores else 0.0
        frr = fn / len(genuine_scores) if genuine_scores else 0.0
        tar = tp / len(genuine_scores) if genuine_scores else 0.0

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        f1 = 2 * prec * tar / (prec + tar) if (prec + tar) > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = thresh

        threshold_sweep.append({
            "threshold": round(thresh, 4),
            "far": round(far, 6),
            "frr": round(frr, 6),
            "tar": round(tar, 6),
        })
        roc_curve.append({"far": round(far, 6), "tar": round(tar, 6)})

    # TAR at specific FAR thresholds
    tar_at_far = {}
    for far_target in far_thresholds:
        best_tar = 0.0
        for entry in threshold_sweep:
            if entry["far"] <= far_target:
                best_tar = max(best_tar, entry["tar"])
        tar_at_far[f"FAR={far_target:.0e}"] = round(best_tar, 4)

    # Operating-point FAR and FRR at recommended threshold
    tp = sum(1 for s in genuine_scores if s >= best_threshold)
    fn = len(genuine_scores) - tp
    fp = sum(1 for s in impostor_scores if s >= best_threshold)
    far_op = fp / len(impostor_scores) if impostor_scores else 0.0
    frr_op = fn / len(genuine_scores) if genuine_scores else 0.0

    return FaceMetricResult(
        far=round(far_op, 6),
        frr=round(frr_op, 6),
        tar_at_far_thresholds=tar_at_far,
        roc_curve_points=roc_curve[:200],
        threshold_sweep=threshold_sweep,
        recommended_threshold=round(best_threshold, 4),
        threshold_recommendation_note=(
            "Threshold selected by maximum F1 on provided dataset. "
            "Validate on held-out data before operational deployment."
        ),
        warnings=warnings,
    )
