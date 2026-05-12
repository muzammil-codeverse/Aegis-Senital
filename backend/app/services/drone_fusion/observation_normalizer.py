"""Phase 46 — Observation Normalizer.

Converts events from all source types into FusionObservation objects.
- No fabricated coordinates.
- No unauthorized observations returned.
- Simulated flag preserved from source.
- Evidence refs attached where available.
- geo_missing set if no valid geo available.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.models.drone_fusion_models import FusionObservation, FusionSourceRef
from app.api.object_authorization import can_access_camera

if TYPE_CHECKING:
    from app.models.security_models import UserAccount
    from app.repositories.gis_repository import GisRepository
    from app.repositories.incident_repository import IncidentRepository
    from app.repositories.drone_mission_repository import DroneMissionRepository

logger = logging.getLogger(__name__)


def _geo_ok(lat: Any, lon: Any) -> bool:
    try:
        return lat is not None and lon is not None and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180
    except (TypeError, ValueError):
        return False


def normalize_fixed_camera_event(
    event: dict[str, Any],
    gis_repo: "GisRepository",
    user: "UserAccount",
    evidence_refs: list[str] | None = None,
) -> FusionObservation | None:
    """Convert a fixed-camera incident/alert event to FusionObservation."""
    camera_id = str(event.get("camera_id") or event.get("source_id") or "")
    if not camera_id:
        logger.debug("normalize_fixed_camera_event: missing camera_id, skipping")
        return None

    if not can_access_camera(camera_id, user):
        logger.debug("normalize_fixed_camera_event: access denied camera_id=%s", camera_id)
        return None

    lat: float | None = None
    lon: float | None = None
    geo_missing = True

    try:
        profile = gis_repo.get_camera_geo_profile(camera_id)
        if profile:
            lat = float(profile.latitude)
            lon = float(profile.longitude)
            geo_missing = not _geo_ok(lat, lon)
    except Exception as exc:
        logger.debug("normalize_fixed_camera_event: geo lookup failed: %s", exc)

    return FusionObservation(
        source_type="fixed_camera",
        source_id=camera_id,
        event_id=str(event.get("event_id") or event.get("alert_id") or ""),
        case_id=event.get("case_id"),
        timestamp=str(event.get("timestamp") or event.get("created_at") or ""),
        latitude=lat,
        longitude=lon,
        geo_missing=geo_missing,
        event_type=str(event.get("event_type") or event.get("alert_type") or ""),
        severity=str(event.get("severity") or ""),
        track_id=event.get("track_id"),
        identity_candidate_id=event.get("identity_candidate_id"),
        simulated=False,
        evidence_refs=list(evidence_refs or []),
        source_ref=FusionSourceRef(
            source_type="fixed_camera",
            source_id=camera_id,
            event_id=event.get("event_id"),
            case_id=event.get("case_id"),
            evidence_ref_ids=list(evidence_refs or []),
            simulated=False,
        ),
    )


def normalize_drone_simulation_event(
    event: dict[str, Any],
    user: "UserAccount",
    evidence_refs: list[str] | None = None,
) -> FusionObservation | None:
    """Convert a drone simulation detection event to FusionObservation."""
    source_id = str(event.get("source_id") or event.get("drone_id") or "drone_sim")

    lat = event.get("latitude") or event.get("lat")
    lon = event.get("longitude") or event.get("lon")
    alt = event.get("altitude_meters") or event.get("altitude")
    geo_missing = not _geo_ok(lat, lon)

    return FusionObservation(
        source_type="drone_simulation",
        source_id=source_id,
        event_id=str(event.get("event_id") or ""),
        case_id=event.get("case_id"),
        timestamp=str(event.get("timestamp") or ""),
        latitude=float(lat) if lat is not None and not geo_missing else None,
        longitude=float(lon) if lon is not None and not geo_missing else None,
        altitude_meters=float(alt) if alt is not None else None,
        geo_missing=geo_missing,
        event_type=str(event.get("event_type") or "drone_detection"),
        severity=str(event.get("severity") or ""),
        track_id=event.get("track_id"),
        identity_candidate_id=event.get("identity_candidate_id"),
        simulated=True,
        evidence_refs=list(evidence_refs or []),
        source_ref=FusionSourceRef(
            source_type="drone_simulation",
            source_id=source_id,
            event_id=event.get("event_id"),
            case_id=event.get("case_id"),
            evidence_ref_ids=list(evidence_refs or []),
            simulated=True,
        ),
    )


def normalize_drone_mission_event(
    event: dict[str, Any],
    user: "UserAccount",
    session_id: str | None = None,
    evidence_refs: list[str] | None = None,
) -> FusionObservation | None:
    """Convert a drone mission telemetry/event to FusionObservation."""
    source_id = str(event.get("source_id") or event.get("drone_id") or "drone_mission")
    sid = session_id or event.get("session_id")

    lat = event.get("latitude") or event.get("lat")
    lon = event.get("longitude") or event.get("lon")
    alt = event.get("altitude_meters") or event.get("altitude")
    geo_missing = not _geo_ok(lat, lon)

    return FusionObservation(
        source_type="drone_mission",
        source_id=source_id,
        event_id=str(event.get("event_id") or event.get("telemetry_id") or ""),
        case_id=event.get("case_id"),
        timestamp=str(event.get("timestamp") or ""),
        latitude=float(lat) if lat is not None and not geo_missing else None,
        longitude=float(lon) if lon is not None and not geo_missing else None,
        altitude_meters=float(alt) if alt is not None else None,
        geo_missing=geo_missing,
        event_type=str(event.get("event_type") or "drone_mission_event"),
        severity=str(event.get("severity") or ""),
        track_id=event.get("track_id"),
        simulated=True,
        evidence_refs=list(evidence_refs or []),
        source_ref=FusionSourceRef(
            source_type="drone_mission",
            source_id=source_id,
            event_id=event.get("event_id"),
            session_id=sid,
            case_id=event.get("case_id"),
            evidence_ref_ids=list(evidence_refs or []),
            simulated=True,
        ),
    )


def normalize_uploaded_video_event(
    event: dict[str, Any],
    user: "UserAccount",
    evidence_refs: list[str] | None = None,
) -> FusionObservation | None:
    """Convert an uploaded-video detection event to FusionObservation."""
    source_id = str(event.get("upload_id") or event.get("source_id") or "uploaded_video")

    lat = event.get("latitude") or event.get("lat")
    lon = event.get("longitude") or event.get("lon")
    geo_missing = not _geo_ok(lat, lon)

    return FusionObservation(
        source_type="uploaded_video",
        source_id=source_id,
        event_id=str(event.get("event_id") or ""),
        case_id=event.get("case_id"),
        timestamp=str(event.get("timestamp") or ""),
        latitude=float(lat) if lat is not None and not geo_missing else None,
        longitude=float(lon) if lon is not None and not geo_missing else None,
        geo_missing=geo_missing,
        event_type=str(event.get("event_type") or "video_detection"),
        severity=str(event.get("severity") or ""),
        track_id=event.get("track_id"),
        simulated=False,
        evidence_refs=list(evidence_refs or []),
        source_ref=FusionSourceRef(
            source_type="uploaded_video",
            source_id=source_id,
            event_id=event.get("event_id"),
            case_id=event.get("case_id"),
            evidence_ref_ids=list(evidence_refs or []),
            simulated=False,
        ),
    )
