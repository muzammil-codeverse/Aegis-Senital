"""Phase 25 — Identity fusion evaluation metrics."""
from __future__ import annotations

import logging

from backend.app.evaluation.schemas import IdentityMetricResult

logger = logging.getLogger(__name__)


def compute_identity_metrics(
    scenario_results: dict[str, dict],
    merge_events: list[dict] | None = None,
) -> IdentityMetricResult:
    """
    Evaluate identity fusion quality.

    scenario_results: { scenario_name: {"tp": int, "fp": int, "fn": int, ...} }
    merge_events: [{"type": "merge|split", "correct": bool, "duration_frames": int}]
    """
    warnings = []
    if not scenario_results and not merge_events:
        warnings.append("No identity fusion data provided")
        return IdentityMetricResult(warnings=warnings)

    merge_events = merge_events or []
    tp = fp = fn = 0
    durations = []
    expired = re_associated = 0

    for ev in merge_events:
        if ev.get("type") == "merge":
            if ev.get("correct"):
                tp += 1
            else:
                fp += 1
        elif ev.get("type") == "split":
            if not ev.get("correct"):
                fn += 1
        if ev.get("type") == "expired":
            expired += 1
        if ev.get("type") == "re_associated":
            re_associated += 1
        if "duration_frames" in ev:
            durations.append(ev["duration_frames"])

    merge_precision = tp / (tp + fp) if (tp + fp) > 0 else None
    merge_recall = tp / (tp + fn) if (tp + fn) > 0 else None
    false_merge_rate = fp / (tp + fp) if (tp + fp) > 0 else None
    false_split_rate = fn / (tp + fn) if (tp + fn) > 0 else None
    avg_duration = sum(durations) / len(durations) if durations else None

    return IdentityMetricResult(
        merge_precision=round(merge_precision, 4) if merge_precision is not None else None,
        merge_recall=round(merge_recall, 4) if merge_recall is not None else None,
        false_merge_rate=round(false_merge_rate, 4) if false_merge_rate is not None else None,
        false_split_rate=round(false_split_rate, 4) if false_split_rate is not None else None,
        identity_persistence_duration_avg=round(avg_duration, 2) if avg_duration is not None else None,
        expired_identity_count=expired,
        re_associated_identity_count=re_associated,
        scenario_results=scenario_results,
        warnings=warnings,
    )
