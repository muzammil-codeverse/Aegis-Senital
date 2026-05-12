"""Phase 46 — Drone/Camera Handoff Service.

Suggests candidate handoffs between fixed cameras and drone observations.
All suggestions are evidence-backed and review-only.
Safe wording enforced. No confirmation language.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from app.api.object_authorization import can_access_camera
from app.models.drone_fusion_models import DroneCameraHandoff, SAFE_SUMMARIES
from inference.config_runtime import load_runtime_config

if TYPE_CHECKING:
    from app.models.security_models import UserAccount
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    from app.repositories.gis_repository import GisRepository
    from app.repositories.incident_repository import IncidentRepository

logger = logging.getLogger(__name__)


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _load_cfg() -> dict[str, Any]:
    return dict(load_runtime_config("drone_fusion").get("drone_fusion") or {})


def _confidence_from_distance(dist_m: float, max_dist_m: float) -> float:
    if dist_m >= max_dist_m:
        return 0.0
    return round(max(0.0, 1.0 - dist_m / max_dist_m) * 0.8, 4)


class HandoffService:

    def __init__(
        self,
        repository: "DroneFusionRepository",
        gis_repo: "GisRepository",
    ) -> None:
        self._repo = repository
        self._gis = gis_repo

    def _get_nearby_cameras(
        self,
        lat: float,
        lon: float,
        radius_meters: float,
        user: "UserAccount",
    ) -> list[dict[str, Any]]:
        try:
            profiles = list(self._gis.list_camera_geo_profiles(user))
        except Exception as exc:
            logger.warning("HandoffService: gis listing failed: %s", exc)
            return []

        nearby = []
        for p in profiles:
            try:
                if not can_access_camera(p.camera_id, user):
                    continue
                dist = _haversine_meters(lat, lon, float(p.latitude), float(p.longitude))
                if dist <= radius_meters:
                    nearby.append({
                        "camera_id": p.camera_id,
                        "name": p.name,
                        "latitude": float(p.latitude),
                        "longitude": float(p.longitude),
                        "distance_meters": round(dist, 2),
                    })
            except Exception:
                continue

        nearby.sort(key=lambda x: x["distance_meters"])
        return nearby

    def suggest_handoffs_for_event(
        self,
        event_id: str,
        user: "UserAccount",
        incident_repo: "IncidentRepository | None" = None,
        radius_meters: float = 200.0,
    ) -> list[DroneCameraHandoff]:
        cfg = _load_cfg()
        max_dist = float(cfg.get("correlation", {}).get("max_spatial_distance_meters", 120))
        radius = min(radius_meters, max_dist * 2)

        event_lat: float | None = None
        event_lon: float | None = None
        camera_id: str | None = None
        case_id: str | None = None

        if incident_repo is not None:
            try:
                event = incident_repo.get_event(event_id)
                if event:
                    event_lat = event.get("latitude") or event.get("lat")
                    event_lon = event.get("longitude") or event.get("lon")
                    camera_id = event.get("camera_id")
                    case_id = event.get("case_id")
            except Exception as exc:
                logger.warning("suggest_handoffs_for_event: incident lookup failed: %s", exc)

        if event_lat is None or event_lon is None:
            return []

        nearby = self._get_nearby_cameras(float(event_lat), float(event_lon), radius, user)
        handoffs: list[DroneCameraHandoff] = []

        for cam in nearby:
            if camera_id and cam["camera_id"] == camera_id:
                continue
            conf = _confidence_from_distance(cam["distance_meters"], radius)
            if conf <= 0:
                continue
            h = DroneCameraHandoff(
                from_source_type="fixed_camera",
                from_source_id=camera_id or "unknown_camera",
                to_source_type="fixed_camera",
                to_source_id=cam["camera_id"],
                reason=f"nearby camera within {cam['distance_meters']:.0f}m of event",
                confidence=conf,
                safe_summary=SAFE_SUMMARIES["handoff"],
                operator_review_required=True,
                event_id=event_id,
                case_id=case_id,
            )
            self._repo.save_handoff(h)
            handoffs.append(h)

        return handoffs

    def suggest_handoffs_for_mission(
        self,
        session_id: str,
        user: "UserAccount",
        mission_repo: "Any | None" = None,
        radius_meters: float = 200.0,
    ) -> list[DroneCameraHandoff]:
        cfg = _load_cfg()
        max_dist = float(cfg.get("correlation", {}).get("max_spatial_distance_meters", 120))
        radius = min(radius_meters, max_dist * 2)

        waypoints: list[dict[str, Any]] = []

        if mission_repo is not None:
            try:
                session = mission_repo.get_session(session_id)
                if session:
                    plan_id = getattr(session, "mission_id", None) or (
                        session.get("mission_id") if isinstance(session, dict) else None
                    )
                    if plan_id:
                        plan = mission_repo.get_mission(plan_id)
                        if plan:
                            wps = getattr(plan, "waypoints", None) or (
                                plan.get("waypoints") if isinstance(plan, dict) else []
                            )
                            for wp in (wps or []):
                                wp_dict = wp if isinstance(wp, dict) else wp.model_dump()
                                waypoints.append(wp_dict)
            except Exception as exc:
                logger.warning("suggest_handoffs_for_mission: mission lookup failed: %s", exc)

        handoffs: list[DroneCameraHandoff] = []
        seen: set[str] = set()

        for wp in waypoints:
            lat = wp.get("latitude") or wp.get("lat")
            lon = wp.get("longitude") or wp.get("lon")
            if lat is None or lon is None:
                continue
            nearby = self._get_nearby_cameras(float(lat), float(lon), radius, user)
            for cam in nearby:
                key = f"{session_id}:{cam['camera_id']}"
                if key in seen:
                    continue
                seen.add(key)
                conf = _confidence_from_distance(cam["distance_meters"], radius)
                if conf <= 0:
                    continue
                h = DroneCameraHandoff(
                    from_source_type="drone_mission",
                    from_source_id=session_id,
                    to_source_type="fixed_camera",
                    to_source_id=cam["camera_id"],
                    reason=f"drone waypoint within {cam['distance_meters']:.0f}m of camera",
                    confidence=conf,
                    safe_summary=SAFE_SUMMARIES["handoff"],
                    operator_review_required=True,
                )
                self._repo.save_handoff(h)
                handoffs.append(h)

        return handoffs

    def suggest_handoffs_near_location(
        self,
        lat: float,
        lon: float,
        radius_meters: float,
        user: "UserAccount",
    ) -> list[DroneCameraHandoff]:
        nearby = self._get_nearby_cameras(lat, lon, radius_meters, user)
        handoffs: list[DroneCameraHandoff] = []

        for cam in nearby:
            conf = _confidence_from_distance(cam["distance_meters"], radius_meters)
            if conf <= 0:
                continue
            h = DroneCameraHandoff(
                from_source_type="drone_simulation",
                from_source_id="drone_sim",
                to_source_type="fixed_camera",
                to_source_id=cam["camera_id"],
                reason=f"aerial observation within {cam['distance_meters']:.0f}m of camera",
                confidence=conf,
                safe_summary=SAFE_SUMMARIES["handoff"],
                operator_review_required=True,
            )
            self._repo.save_handoff(h)
            handoffs.append(h)

        return handoffs


def get_handoff_service(
    repository: "DroneFusionRepository | None" = None,
    gis_repo: "GisRepository | None" = None,
) -> HandoffService:
    if repository is None:
        from app.repositories.drone_fusion_repository import get_drone_fusion_repository
        repository = get_drone_fusion_repository()
    if gis_repo is None:
        from app.repositories.gis_repository import GisRepository
        gis_repo = GisRepository()
    return HandoffService(repository=repository, gis_repo=gis_repo)
