"""Phase 46 — Cross-Source Fusion Service.

Correlates FusionObservations from different source types using
temporal, spatial, appearance, event-type, and mission-context scoring.

Rules:
- Correlation requires at least two evidence-backed observations (source_ref present).
- No source refs → no correlation.
- Low confidence remains below threshold and is suppressed.
- Safe summary enforced; forbidden phrases rejected.
- All results carry operator_review_required=True.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.models.drone_fusion_models import (
    CrossSourceCorrelation,
    FusionConfidenceBreakdown,
    FusionObservation,
    SAFE_SUMMARIES,
)
from inference.config_runtime import load_runtime_config

if TYPE_CHECKING:
    from app.models.security_models import UserAccount
    from app.repositories.drone_fusion_repository import DroneFusionRepository

logger = logging.getLogger(__name__)


def _load_cfg() -> dict[str, Any]:
    return dict(load_runtime_config("drone_fusion").get("drone_fusion") or {})


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _compute_time_score(ts_a: str, ts_b: str, max_delta_seconds: float) -> float:
    dt_a = _parse_ts(ts_a)
    dt_b = _parse_ts(ts_b)
    if dt_a is None or dt_b is None:
        return 0.0
    delta = abs((dt_a - dt_b).total_seconds())
    if delta >= max_delta_seconds:
        return 0.0
    return max(0.0, 1.0 - delta / max_delta_seconds)


def _compute_geo_score(
    obs_a: FusionObservation,
    obs_b: FusionObservation,
    max_distance_meters: float,
) -> float:
    if obs_a.geo_missing or obs_b.geo_missing:
        return 0.0
    if obs_a.latitude is None or obs_b.latitude is None:
        return 0.0
    dist = _haversine_meters(
        obs_a.latitude, obs_a.longitude or 0.0,
        obs_b.latitude, obs_b.longitude or 0.0,
    )
    if dist >= max_distance_meters:
        return 0.0
    return max(0.0, 1.0 - dist / max_distance_meters)


def _compute_event_type_score(type_a: str | None, type_b: str | None) -> float:
    if not type_a or not type_b:
        return 0.5
    if type_a == type_b:
        return 1.0
    high_risk = {"weapon_detected", "intrusion_detected", "threat_detected", "drone_detection"}
    if type_a in high_risk and type_b in high_risk:
        return 0.8
    return 0.3


def _compute_mission_context_score(obs_a: FusionObservation, obs_b: FusionObservation) -> float:
    has_mission = obs_a.source_type in ("drone_mission", "drone_simulation") or \
                  obs_b.source_type in ("drone_mission", "drone_simulation")
    if has_mission:
        return 0.7
    return 0.3


def _compute_appearance_score(obs_a: FusionObservation, obs_b: FusionObservation) -> float:
    if obs_a.appearance_ref and obs_b.appearance_ref:
        if obs_a.appearance_ref == obs_b.appearance_ref:
            return 0.9
        return 0.4
    if obs_a.track_id and obs_b.track_id and obs_a.track_id == obs_b.track_id:
        return 0.8
    return 0.0


VALID_SOURCE_PAIRS = {
    frozenset({"fixed_camera", "drone_simulation"}),
    frozenset({"fixed_camera", "drone_mission"}),
    frozenset({"drone_mission", "uploaded_video"}),
    frozenset({"drone_simulation", "uploaded_video"}),
    frozenset({"fixed_camera", "uploaded_video"}),
}


class CrossSourceFusionService:

    def __init__(self, repository: "DroneFusionRepository") -> None:
        self._repo = repository

    def _get_weights(self, cfg: dict[str, Any]) -> dict[str, float]:
        scoring = cfg.get("scoring") or {}
        return {
            "time": float(scoring.get("time_weight", 0.30)),
            "geo": float(scoring.get("geo_weight", 0.25)),
            "appearance": float(scoring.get("appearance_weight", 0.20)),
            "event_type": float(scoring.get("event_type_weight", 0.15)),
            "mission_context": float(scoring.get("mission_context_weight", 0.10)),
        }

    def correlate(
        self,
        observations: list[FusionObservation],
        user: "UserAccount",
        case_id: str | None = None,
        event_id: str | None = None,
    ) -> list[CrossSourceCorrelation]:
        cfg = _load_cfg()
        corr_cfg = cfg.get("correlation") or {}
        max_time = float(corr_cfg.get("max_time_delta_seconds", 20))
        max_dist = float(corr_cfg.get("max_spatial_distance_meters", 120))
        min_conf = float(corr_cfg.get("min_fusion_confidence", 0.35))
        weights = self._get_weights(cfg)

        eligible = [o for o in observations if o.source_ref is not None]

        correlations: list[CrossSourceCorrelation] = []
        checked: set[frozenset[str]] = set()

        for i, obs_a in enumerate(eligible):
            for obs_b in eligible[i + 1:]:
                pair_key = frozenset({obs_a.observation_id, obs_b.observation_id})
                if pair_key in checked:
                    continue
                checked.add(pair_key)

                source_pair = frozenset({obs_a.source_type, obs_b.source_type})
                if source_pair not in VALID_SOURCE_PAIRS:
                    continue

                if not obs_a.evidence_refs and not obs_b.evidence_refs:
                    if not (obs_a.event_id or obs_b.event_id):
                        logger.debug("Skipping pair: no evidence refs and no event_ids")
                        continue

                time_score = _compute_time_score(obs_a.timestamp, obs_b.timestamp, max_time)
                geo_score = _compute_geo_score(obs_a, obs_b, max_dist)
                appearance_score = _compute_appearance_score(obs_a, obs_b)
                event_type_score = _compute_event_type_score(obs_a.event_type, obs_b.event_type)
                mission_score = _compute_mission_context_score(obs_a, obs_b)

                confidence = (
                    time_score * weights["time"]
                    + geo_score * weights["geo"]
                    + appearance_score * weights["appearance"]
                    + event_type_score * weights["event_type"]
                    + mission_score * weights["mission_context"]
                )

                if confidence < min_conf:
                    continue

                breakdown = FusionConfidenceBreakdown(
                    time_score=round(time_score, 4),
                    geo_score=round(geo_score, 4),
                    appearance_score=round(appearance_score, 4),
                    event_type_score=round(event_type_score, 4),
                    mission_context_score=round(mission_score, 4),
                    weighted_total=round(confidence, 4),
                )

                merged_evidence = list({*obs_a.evidence_refs, *obs_b.evidence_refs})

                corr = CrossSourceCorrelation(
                    primary_observation_id=obs_a.observation_id,
                    matched_observation_id=obs_b.observation_id,
                    source_pair=sorted({obs_a.source_type, obs_b.source_type}),
                    confidence=round(confidence, 4),
                    confidence_breakdown=breakdown,
                    safe_summary=SAFE_SUMMARIES["correlation"],
                    operator_review_required=True,
                    review_status="pending",
                    case_id=case_id or obs_a.case_id or obs_b.case_id,
                    event_id=event_id or obs_a.event_id or obs_b.event_id,
                    evidence_refs=merged_evidence,
                )

                self._repo.save_correlation(corr)
                correlations.append(corr)

        return correlations

    def get_fusion_stats(self) -> dict[str, Any]:
        stats = self._repo.count_stats()
        corrs = self._repo.list_correlations(limit=1000)
        avg_conf = 0.0
        if corrs:
            avg_conf = sum(c.confidence for c in corrs) / len(corrs)
        stats["average_confidence"] = round(avg_conf, 4)
        return stats


def get_fusion_service(repository: "DroneFusionRepository | None" = None) -> CrossSourceFusionService:
    if repository is None:
        from app.repositories.drone_fusion_repository import get_drone_fusion_repository
        repository = get_drone_fusion_repository()
    return CrossSourceFusionService(repository)
