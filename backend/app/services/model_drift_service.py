"""Drift monitoring — aggregates only observed signals; never fabricates stability."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.repositories.analytics_repository import AnalyticsRepository
from app.services.model_governance_service import PROJECT_ROOT, load_model_governance_config

logger = logging.getLogger(__name__)


def _bins(confidences: list[float], n_bins: int) -> dict[str, int]:
    if not confidences or n_bins <= 0:
        return {}
    counts = [0] * n_bins
    for raw in confidences:
        c = float(raw)
        c = min(1.0, max(0.0, c))
        idx = min(n_bins - 1, int(c * n_bins))
        counts[idx] += 1
    return {f"bin_{i}": counts[i] for i in range(n_bins)}


def _event_matches_model(ev: dict[str, Any], model_id: str) -> bool:
    mid = model_id.lower()
    et = str(ev.get("event_type") or "").lower()
    if mid in et:
        return True
    if "weapon" in mid and "weapon" in et:
        return True
    if "phone" in mid and "phone" in et:
        return True
    if str(ev.get("model_id") or "") == model_id:
        return True
    return False


def summarize_drift_for_model(
    model_id: str,
    *,
    window: str = "24h",
    analytics: AnalyticsRepository | None = None,
) -> dict[str, Any]:
    cfg = dict((load_model_governance_config().get("model_governance") or {}).get("drift") or {})
    if not bool(cfg.get("enabled", True)):
        return {
            "model_id": model_id,
            "window": window,
            "sample_count": 0,
            "class_distribution": {},
            "confidence_distribution": {},
            "latency": {},
            "drift_status": "insufficient_data",
            "recommendations": ["drift_monitoring_disabled"],
        }

    repo = analytics or AnalyticsRepository()
    n_bins = int(cfg.get("confidence_distribution_bins") or 10)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    time_range = {"start": start.isoformat(), "end": end.isoformat()}

    try:
        events = repo.get_events(time_range, {"limit": 5000, "bus_limit": 2000})
    except Exception as exc:
        logger.info("drift_events_unavailable model=%s err=%s", model_id, exc)
        events = []

    confidences: list[float] = []
    classes: list[str] = []
    latency_vals: list[float] = []
    per_camera: Counter[str] = Counter()

    for ev in events:
        if not _event_matches_model(ev, model_id):
            continue
        if ev.get("confidence") is not None:
            try:
                confidences.append(float(ev.get("confidence")))
            except (TypeError, ValueError):
                pass
        cls = ev.get("class_name") or ev.get("label")
        if cls:
            classes.append(str(cls))
        cam = ev.get("camera_id") or ev.get("stream_id")
        if cam:
            per_camera[str(cam)] += 1
        lat = ev.get("latency_ms")
        if lat is not None:
            try:
                latency_vals.append(float(lat))
            except (TypeError, ValueError):
                pass

    sample_count = len(confidences) + len(classes) + len(latency_vals)
    if sample_count == 0:
        return {
            "model_id": model_id,
            "window": window,
            "sample_count": 0,
            "class_distribution": {},
            "confidence_distribution": {},
            "latency": {},
            "drift_status": "insufficient_data",
            "recommendations": ["collect_more_telemetry_for_this_model"],
        }

    class_distribution = dict(Counter(classes).most_common(50))
    conf_dist = _bins(confidences, n_bins) if confidences else {}
    latency_summary: dict[str, Any] = {}
    if latency_vals:
        sorted_lat = sorted(latency_vals)
        idx = max(0, int(0.95 * (len(sorted_lat) - 1)))
        latency_summary = {
            "count": len(sorted_lat),
            "mean_ms": round(sum(sorted_lat) / len(sorted_lat), 3),
            "p95_ms": round(sorted_lat[idx], 3),
        }

    drift_status = "stable"
    recommendations: list[str] = []
    if len(confidences) < 10:
        drift_status = "insufficient_data"
        recommendations.append("insufficient_confidence_samples")
    elif confidences:
        mean_c = sum(confidences) / len(confidences)
        if mean_c < 0.25 or mean_c > 0.98:
            drift_status = "warning"
            recommendations.append("confidence_mean_shift_investigate_data_pipeline")

    return {
        "model_id": model_id,
        "window": window,
        "sample_count": sample_count,
        "class_distribution": class_distribution,
        "confidence_distribution": conf_dist,
        "latency": latency_summary,
        "per_camera_detection_counts": dict(per_camera),
        "drift_status": drift_status,
        "recommendations": recommendations,
    }


def drift_storage_dir() -> Path:
    cfg = dict((load_model_governance_config().get("model_governance") or {}).get("drift") or {})
    rel = str(cfg.get("storage_dir") or "storage/model_drift")
    return PROJECT_ROOT / rel
