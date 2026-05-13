from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from geopy.distance import geodesic
from shapely.geometry import Point, Polygon

from app.api.object_authorization import can_access_camera
from app.models.gis_models import (
    CameraFieldOfView,
    CameraGeoProfile,
    DronePathOverlay,
    GeoFenceZone,
    GeoPoint,
    GisPublicConfig,
    MapLayerResponse,
    MapViewportRequest,
    NearbyCameraResult,
    RiskHeatmapCell,
)
from app.models.security_models import UserAccount
from inference.config_runtime import load_runtime_config

if TYPE_CHECKING:
    from app.repositories.gis_repository import GisRepository


def load_gis_settings() -> dict[str, Any]:
    return dict(load_runtime_config("gis").get("gis") or {})


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not (-90.0 <= float(latitude) <= 90.0):
        raise ValueError("latitude must be between -90 and 90")
    if not (-180.0 <= float(longitude) <= 180.0):
        raise ValueError("longitude must be between -180 and 180")


def normalize_profile(profile: CameraGeoProfile, defaults: dict[str, Any] | None = None) -> CameraGeoProfile:
    cfg = defaults or (load_gis_settings().get("cameras") or {})
    fov = float(profile.fov_degrees or cfg.get("default_fov_degrees", 75))
    radius = float(profile.coverage_radius_meters or cfg.get("default_coverage_radius_meters", 80))
    return profile.model_copy(
        update={
            "fov_degrees": fov,
            "coverage_radius_meters": radius,
            "heading_degrees": float(profile.heading_degrees or 0.0) % 360.0,
        }
    )


def compute_camera_fov_polygon(profile: CameraGeoProfile) -> list[GeoPoint]:
    """Deterministic wedge polygon: camera position + arc at coverage radius."""
    prof = normalize_profile(profile)
    lat = float(prof.latitude)
    lon = float(prof.longitude)
    heading = float(prof.heading_degrees or 0.0)
    half = float(prof.fov_degrees or 60.0) / 2.0
    radius_m = float(prof.coverage_radius_meters or 50.0)
    steps = 16
    pts: list[GeoPoint] = [GeoPoint(latitude=lat, longitude=lon)]
    for i in range(steps + 1):
        bearing = heading - half + (2.0 * half) * (i / steps)
        dest = geodesic(meters=radius_m).destination(point=(lat, lon), bearing=bearing % 360.0)
        pts.append(GeoPoint(latitude=float(dest.latitude), longitude=float(dest.longitude)))
    pts.append(GeoPoint(latitude=lat, longitude=lon))
    return pts


def distance_meters(point_a: GeoPoint, point_b: GeoPoint) -> float:
    return float(geodesic((point_a.latitude, point_a.longitude), (point_b.latitude, point_b.longitude)).meters)


def point_in_geofence(point: GeoPoint, geofence: GeoFenceZone) -> bool:
    if not geofence.active:
        return False
    coords = [(p.longitude, p.latitude) for p in geofence.polygon]
    if len(coords) < 3:
        return False
    poly = Polygon(coords)
    return bool(poly.contains(Point(point.longitude, point.latitude)))


def find_nearby_cameras(
    repo: GisRepository,
    user: UserAccount | None,
    latitude: float,
    longitude: float,
    radius_meters: float,
) -> list[NearbyCameraResult]:
    validate_coordinates(latitude, longitude)
    origin = GeoPoint(latitude=latitude, longitude=longitude)
    results: list[NearbyCameraResult] = []
    for profile in repo.list_camera_geo_profiles(user):
        try:
            validate_coordinates(profile.latitude, profile.longitude)
        except ValueError:
            continue
        d = distance_meters(origin, GeoPoint(latitude=profile.latitude, longitude=profile.longitude))
        if d <= radius_meters:
            results.append(
                NearbyCameraResult(
                    camera_id=profile.camera_id,
                    name=profile.name or profile.camera_id,
                    distance_meters=round(d, 3),
                    latitude=profile.latitude,
                    longitude=profile.longitude,
                )
            )
    results.sort(key=lambda r: r.distance_meters)
    return results


def _severity_weight(severity: str | None, weights: dict[str, float]) -> float:
    key = str(severity or "medium").lower()
    return float(weights.get(key, weights.get("medium", 3.0)))


def compute_risk_heatmap(
    repo: GisRepository,
    user: UserAccount | None,
    start_time: str | None,
    end_time: str | None,
    severity: str | None,
    event_type: str | None,
    camera_id: str | None,
    case_id: str | None,
    source_type: str | None,
) -> list[RiskHeatmapCell]:
    cfg = load_gis_settings()
    hm = cfg.get("heatmap") or {}
    if not bool(hm.get("enabled", True)):
        return []
    radius_m = float(hm.get("radius_meters", 250))
    weights = dict(hm.get("severity_weights") or {})
    markers = repo.get_event_markers(
        user=user,
        start_time=start_time,
        end_time=end_time,
        severity=severity,
        event_type=event_type,
        camera_id=camera_id,
        case_id=case_id,
        source_type=source_type,
    )
    meters_per_degree_lat = 111_320.0
    dlat = radius_m / meters_per_degree_lat
    cells: dict[str, dict[str, Any]] = {}
    for m in markers:
        lat = float(m.latitude)
        lon = float(m.longitude)
        cos_lat = math.cos(math.radians(max(abs(lat), 1e-6)))
        dlon = dlat / cos_lat
        ilat = int(round(lat / dlat))
        ilon = int(round(lon / dlon))
        cell_id = f"{ilat}:{ilon}"
        w = _severity_weight(m.severity, weights)
        if cell_id not in cells:
            cells[cell_id] = {
                "weight": 0.0,
                "count": 0,
                "lat_sum": 0.0,
                "lon_sum": 0.0,
                "severity": m.severity,
            }
        c = cells[cell_id]
        c["weight"] += w
        c["count"] += 1
        c["lat_sum"] += lat
        c["lon_sum"] += lon
    out: list[RiskHeatmapCell] = []
    for cid, payload in cells.items():
        n = max(1, int(payload["count"]))
        out.append(
            RiskHeatmapCell(
                cell_id=cid,
                center_latitude=payload["lat_sum"] / n,
                center_longitude=payload["lon_sum"] / n,
                weight=round(float(payload["weight"]), 4),
                event_count=int(payload["count"]),
                severity=str(payload.get("severity") or "medium"),
            )
        )
    out.sort(key=lambda c: c.weight, reverse=True)
    try:
        import networkx as nx

        graph = nx.Graph()
        for cell in out:
            graph.add_node(cell.cell_id, weight=cell.weight)
        _ = graph.number_of_nodes()
    except Exception:
        pass
    return out


def public_gis_config() -> GisPublicConfig:
    raw = load_gis_settings()
    provider = str((raw.get("provider") or {}).get("default") or "local_mock")
    return GisPublicConfig(
        enabled=bool(raw.get("enabled", True)),
        provider=provider,
        map=dict(raw.get("map") or {}),
        cameras=dict(raw.get("cameras") or {}),
        events=dict(raw.get("events") or {}),
        heatmap=dict(raw.get("heatmap") or {}),
        geofencing=dict(raw.get("geofencing") or {}),
        frontend=dict(raw.get("frontend") or {}),
    )


def _fallback_drone_profile(user: UserAccount | None) -> CameraGeoProfile | None:
    try:
        from app.services.drone.drone_simulation_service import get_drone_simulation_service

        service = get_drone_simulation_service()
    except Exception:
        return None
    if user is not None and not can_access_camera(user, service.drone_id):
        return None
    telemetry = service.latest_telemetry()
    default_home = dict((service.config.get("gis") or {}).get("default_home") or {})
    latitude = telemetry.latitude if telemetry and telemetry.latitude is not None else default_home.get("latitude")
    longitude = telemetry.longitude if telemetry and telemetry.longitude is not None else default_home.get("longitude")
    if latitude is None or longitude is None:
        return None
    altitude = (
        telemetry.altitude_meters
        if telemetry and telemetry.altitude_meters is not None
        else default_home.get("altitude_meters")
    )
    yaw = telemetry.orientation.yaw if telemetry and telemetry.orientation is not None else 0.0
    return CameraGeoProfile(
        camera_id=service.drone_id,
        name="Simulated Drone Feed",
        latitude=float(latitude),
        longitude=float(longitude),
        altitude_meters=float(altitude) if altitude is not None else None,
        heading_degrees=float(yaw or 0.0),
        fov_degrees=70.0,
        coverage_radius_meters=150.0,
        region="simulated_airspace",
        metadata={
            "source_type": "drone_simulation",
            "simulated": True,
            "provider": "cosys_airsim",
            "camera_name": telemetry.camera_name if telemetry is not None else "front_center",
            "safety_badge": "Simulated drone feed",
        },
    )


def _build_mission_route_layers() -> dict[str, list[dict[str, Any]]]:
    try:
        from app.repositories.drone_mission_repository import get_drone_mission_repository
    except Exception:
        return {
            "drone_mission_routes": [],
            "drone_mission_waypoints": [],
            "active_mission_paths": [],
            "completed_mission_paths": [],
        }

    repo = get_drone_mission_repository()
    missions = repo.list_missions(limit=200, offset=0)
    routes: list[dict[str, Any]] = []
    waypoints: list[dict[str, Any]] = []
    active_paths: list[dict[str, Any]] = []
    completed_paths: list[dict[str, Any]] = []
    for mission in missions:
        pts = [
            {
                "latitude": wp.latitude,
                "longitude": wp.longitude,
                "altitude_meters": wp.altitude_meters,
                "sequence_index": wp.sequence_index,
                "action": (wp.metadata or {}).get("action"),
            }
            for wp in mission.waypoints
            if wp.latitude is not None and wp.longitude is not None
        ]
        route_item = {
            "mission_id": mission.mission_id,
            "name": mission.name,
            "status": mission.status.value,
            "simulated": mission.simulated,
            "operator_review_required": mission.operator_review_required,
            "safe_label": mission.safe_label,
            "points": pts,
            "metadata": mission.metadata or {},
        }
        routes.append(route_item)
        waypoints.extend(
            {
                "mission_id": mission.mission_id,
                "name": mission.name,
                "status": mission.status.value,
                "waypoint_index": item["sequence_index"],
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "altitude_meters": item["altitude_meters"],
                "action": item.get("action"),
                "simulated": True,
                "operator_review_required": True,
            }
            for item in pts
        )
        sessions = repo.list_sessions(mission_id=mission.mission_id, limit=20, offset=0)
        latest_session = sessions[-1] if sessions else None
        session_status = str(getattr(latest_session.status, "value", latest_session.status) if latest_session else mission.status.value)
        if session_status in {"executing", "paused"}:
            active_paths.append({
                **route_item,
                "session_id": latest_session.session_id if latest_session else None,
                "current_waypoint_index": int(latest_session.current_waypoint_index) if latest_session else 0,
                "progress_percent": float(latest_session.progress_percent) if latest_session else 0.0,
            })
        if session_status in {"completed", "cancelled", "failed"} or mission.status.value in {"completed", "cancelled", "failed"}:
            completed_paths.append({
                **route_item,
                "session_id": latest_session.session_id if latest_session else None,
                "completion_percent": float(latest_session.progress_percent) if latest_session else 0.0,
            })
    return {
        "drone_mission_routes": routes,
        "drone_mission_waypoints": waypoints,
        "active_mission_paths": active_paths,
        "completed_mission_paths": completed_paths,
    }


def _build_fixed_camera_handoff_layers(cameras: list[CameraGeoProfile]) -> list[dict[str, Any]]:
    try:
        from app.repositories.drone_fusion_repository import get_drone_fusion_repository
    except Exception:
        return []

    by_camera = {camera.camera_id: camera for camera in cameras}
    handoffs: list[dict[str, Any]] = []
    for handoff in get_drone_fusion_repository().list_handoffs(limit=200):
        from_profile = by_camera.get(handoff.from_source_id)
        if from_profile is None and str(handoff.from_source_id).startswith("drone_sim_01"):
            from_profile = by_camera.get("drone_sim_01")
        to_profile = by_camera.get(handoff.to_source_id)
        if to_profile is None and str(handoff.to_source_id).startswith("drone_sim_01"):
            to_profile = by_camera.get("drone_sim_01")
        if from_profile is None or to_profile is None:
            continue
        handoffs.append(
            {
                "handoff_id": handoff.handoff_id,
                "from_source_id": handoff.from_source_id,
                "to_source_id": handoff.to_source_id,
                "confidence": float(handoff.confidence),
                "simulated": True,
                "operator_review_required": True,
                "safe_summary": handoff.safe_summary,
                "from": {"latitude": from_profile.latitude, "longitude": from_profile.longitude},
                "to": {"latitude": to_profile.latitude, "longitude": to_profile.longitude},
            }
        )
    return handoffs


def build_map_layers(
    repo: GisRepository,
    user: UserAccount | None,
    viewport: MapViewportRequest | None,
    *,
    start_time: str | None,
    end_time: str | None,
    severity: str | None,
    event_type: str | None,
    camera_id: str | None,
    case_id: str | None,
    source_type: str | None,
    include_fov: bool = True,
    include_heatmap: bool = True,
) -> MapLayerResponse:
    cfg = load_gis_settings()
    cameras_cfg = cfg.get("cameras") or {}
    require_loc = bool(cameras_cfg.get("require_location_for_map_display", True))
    cameras = []
    for p in repo.list_camera_geo_profiles(user):
        try:
            validate_coordinates(p.latitude, p.longitude)
            cameras.append(p)
        except ValueError:
            if not require_loc:
                cameras.append(p)
    fallback_drone = _fallback_drone_profile(user)
    if fallback_drone is not None and all(camera.camera_id != fallback_drone.camera_id for camera in cameras):
        cameras.append(fallback_drone)

    fovs: list[CameraFieldOfView] = []
    if include_fov and bool(cameras_cfg.get("show_field_of_view_cones", True)):
        for p in cameras:
            poly = compute_camera_fov_polygon(p)
            fovs.append(
                CameraFieldOfView(
                    camera_id=p.camera_id,
                    polygon=poly,
                    heading_degrees=float(p.heading_degrees or 0.0),
                    fov_degrees=float(p.fov_degrees or 0.0),
                    coverage_radius_meters=float(p.coverage_radius_meters or 0.0),
                )
            )

    events = repo.get_event_markers(
        user=user,
        start_time=start_time,
        end_time=end_time,
        severity=severity,
        event_type=event_type,
        camera_id=camera_id,
        case_id=case_id,
        source_type=source_type,
    )
    cases = repo.get_case_markers(
        user=user,
        start_time=start_time,
        end_time=end_time,
        severity=severity,
        camera_id=camera_id,
        case_id=case_id,
    )
    heatmap_cells: list[RiskHeatmapCell] = []
    if include_heatmap:
        heatmap_cells = compute_risk_heatmap(
            repo,
            user,
            start_time,
            end_time,
            severity,
            event_type,
            camera_id,
            case_id,
            source_type,
        )
    geofences = repo.list_geofences(user)
    drone_paths: list[DronePathOverlay] = []
    try:
        from app.services.drone.drone_simulation_session_manager import get_drone_simulation_session_manager

        manager = get_drone_simulation_session_manager()
        camera_ids = {cam.camera_id for cam in cameras}
        points = []
        for point in manager.get_flight_path():
            if point.camera_id not in camera_ids:
                continue
            points.append(
                GeoPoint(
                    latitude=point.latitude,
                    longitude=point.longitude,
                    altitude_meters=point.altitude_meters,
                )
            )
        latest_telemetry = manager.get_latest_telemetry()
        if points:
            drone_paths.append(
                DronePathOverlay(
                    drone_id="drone_sim_01",
                    source_type="drone_simulation",
                    simulated=True,
                    points=points,
                    latest_timestamp=latest_telemetry.timestamp if latest_telemetry is not None else None,
                )
            )
    except Exception:
        drone_paths = []
    stream_status: dict[str, Any] = {}
    try:
        from app.services.stream_session_manager import get_stream_session_manager
        from app.services.drone.drone_simulation_session_manager import get_drone_simulation_session_manager

        for cam in cameras:
            if cam.metadata.get("source_type") == "drone_simulation" or cam.camera_id == "drone_sim_01":
                try:
                    stream_status[cam.camera_id] = get_drone_simulation_session_manager().get_session_status().model_dump(mode="json")
                except Exception:
                    stream_status[cam.camera_id] = {"status": "unknown"}
                continue
            try:
                stream_status[cam.camera_id] = get_stream_session_manager().get_stream_state(cam.camera_id)
            except Exception:
                stream_status[cam.camera_id] = {"status": "unknown"}
    except Exception:
        stream_status = {}

    mission_layers = _build_mission_route_layers()
    handoff_layers = _build_fixed_camera_handoff_layers(cameras)

    return MapLayerResponse(
        cameras=cameras,
        camera_fovs=fovs,
        event_markers=events,
        case_markers=cases,
        heatmap_cells=heatmap_cells,
        geofences=geofences,
        drone_paths=drone_paths,
        drone_mission_routes=mission_layers.get("drone_mission_routes", []),
        drone_mission_waypoints=mission_layers.get("drone_mission_waypoints", []),
        active_mission_paths=mission_layers.get("active_mission_paths", []),
        completed_mission_paths=mission_layers.get("completed_mission_paths", []),
        fixed_camera_handoffs=handoff_layers,
        stream_status_by_camera=stream_status,
        viewport=viewport,
    )


def evaluate_gis_readiness() -> dict[str, Any]:
    """Used by runtime health and validate_runtime (production map API keys)."""
    raw = load_gis_settings()
    enabled = bool(raw.get("enabled", True))
    provider_cfg = raw.get("provider") or {}
    provider = str(provider_cfg.get("default") or "local_mock").lower()
    require_key = bool(provider_cfg.get("require_api_key_in_production", True))
    import os

    prod = (os.getenv("APP_ENV") or "").lower() in {"prod", "production"}
    fe = raw.get("frontend") or {}
    mapbox_var = str(fe.get("mapbox_env_var") or "VITE_MAPBOX_TOKEN")
    google_var = str(fe.get("google_maps_env_var") or "VITE_GOOGLE_MAPS_API_KEY")
    last_error = None
    status = "healthy"
    if not enabled:
        return {"enabled": False, "status": "disabled", "provider": provider, "last_error": None}
    if prod and require_key and provider not in {"local_mock", "mock", "none"}:
        if provider == "mapbox" and not (os.getenv(mapbox_var) or "").strip():
            status = "failed"
            last_error = f"Missing {mapbox_var} for production mapbox provider"
        if provider in {"google_maps", "google"} and not (os.getenv(google_var) or "").strip():
            status = "failed"
            last_error = f"Missing {google_var} for production google_maps provider"
    return {"enabled": True, "status": status, "provider": provider, "last_error": last_error}


class GisService:
    def __init__(self, repository: GisRepository | None = None) -> None:
        from app.repositories.gis_repository import get_gis_repository

        self._repo = repository or get_gis_repository()

    @property
    def repository(self) -> GisRepository:
        return self._repo


_svc: GisService | None = None


def reset_gis_service_singleton() -> None:
    global _svc
    _svc = None


def get_gis_service() -> GisService:
    global _svc
    if _svc is None:
        _svc = GisService()
    return _svc
