from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.api.object_authorization import can_access_camera
from app.models.gis_models import CameraGeoProfile
from app.models.investigation_models import CameraGraphEdge, CameraGraphNode
from inference.config_runtime import load_runtime_config

if TYPE_CHECKING:
    from app.models.security_models import UserAccount
    from app.repositories.gis_repository import GisRepository


def _load_cfg() -> dict[str, Any]:
    return dict((load_runtime_config("investigation").get("investigation") or {}).get("camera_graph") or {})


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_camera_graph(
    gis_repo: GisRepository,
    user: UserAccount,
) -> tuple[list[CameraGraphNode], list[CameraGraphEdge]]:
    cfg = _load_cfg()
    max_dist = float(cfg.get("max_edge_distance_meters", 500))
    walk_mps = float(cfg.get("walking_speed_mps", 1.4))
    run_mps = float(cfg.get("running_speed_mps", 3.5))
    vehicle_mps = float(cfg.get("vehicle_speed_mps", 8.0))

    profiles = list(gis_repo.list_camera_geo_profiles(user))
    drone_profile = _drone_profile_for_user(user)
    if drone_profile is not None and all(profile.camera_id != drone_profile.camera_id for profile in profiles):
        profiles.append(drone_profile)
    nodes: list[CameraGraphNode] = []
    for p in profiles:
        nodes.append(
            CameraGraphNode(
                camera_id=p.camera_id,
                name=p.name,
                source_type=str((p.metadata or {}).get("source_type") or "live_stream"),
                simulated=bool((p.metadata or {}).get("simulated", False)),
                latitude=p.latitude,
                longitude=p.longitude,
                heading_degrees=p.heading_degrees,
                fov_degrees=p.fov_degrees,
                coverage_radius_meters=p.coverage_radius_meters,
                region=p.region,
                metadata=dict(p.metadata or {}),
            )
        )

    edges: list[CameraGraphEdge] = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            dist = _haversine_meters(a.latitude, a.longitude, b.latitude, b.longitude)
            if dist > max_dist:
                continue
            fov_overlap = _fov_overlap(a, b)
            walk_s = dist / walk_mps if walk_mps > 0 else 9999
            run_s = dist / run_mps if run_mps > 0 else 9999
            vehicle_s = dist / vehicle_mps if vehicle_mps > 0 else 9999
            score = _transition_score(dist, max_dist, fov_overlap)
            edge = CameraGraphEdge(
                from_camera_id=a.camera_id,
                to_camera_id=b.camera_id,
                distance_meters=round(dist, 2),
                estimated_walk_seconds=round(walk_s, 1),
                estimated_run_seconds=round(run_s, 1),
                estimated_vehicle_seconds=round(vehicle_s, 1),
                transition_score=round(score, 4),
                fov_overlap=fov_overlap,
                geofence_penalty=0.0,
            )
            edges.append(edge)
            edges.append(
                CameraGraphEdge(
                    from_camera_id=b.camera_id,
                    to_camera_id=a.camera_id,
                    distance_meters=edge.distance_meters,
                    estimated_walk_seconds=edge.estimated_walk_seconds,
                    estimated_run_seconds=edge.estimated_run_seconds,
                    estimated_vehicle_seconds=edge.estimated_vehicle_seconds,
                    transition_score=edge.transition_score,
                    fov_overlap=edge.fov_overlap,
                    geofence_penalty=edge.geofence_penalty,
                )
            )

    return nodes, edges


def _drone_profile_for_user(user: UserAccount | None) -> CameraGeoProfile | None:
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
    heading = telemetry.orientation.yaw if telemetry and telemetry.orientation is not None else 0.0
    return CameraGeoProfile(
        camera_id=service.drone_id,
        name="Simulated Drone Feed",
        latitude=float(latitude),
        longitude=float(longitude),
        altitude_meters=float(altitude) if altitude is not None else None,
        heading_degrees=float(heading or 0.0),
        fov_degrees=70.0,
        coverage_radius_meters=150.0,
        region="simulated_airspace",
        metadata={
            "source_type": "drone_simulation",
            "simulated": True,
            "provider": "cosys_airsim",
            "camera_name": telemetry.camera_name if telemetry is not None else "front_center",
        },
    )


def _fov_overlap(a: CameraGraphNode, b: CameraGraphNode) -> bool:
    dist = _haversine_meters(a.latitude, a.longitude, b.latitude, b.longitude)
    return dist <= (a.coverage_radius_meters + b.coverage_radius_meters)


def _transition_score(dist_m: float, max_dist_m: float, fov_overlap: bool) -> float:
    if max_dist_m <= 0:
        return 0.0
    proximity = max(0.0, 1.0 - (dist_m / max_dist_m))
    bonus = 0.15 if fov_overlap else 0.0
    return min(1.0, proximity + bonus)


def get_edges_from(
    edges: list[CameraGraphEdge],
    camera_id: str,
) -> list[CameraGraphEdge]:
    return [e for e in edges if e.from_camera_id == camera_id]


def estimate_travel_seconds(
    edge: CameraGraphEdge,
    mode: str = "walk",
) -> float:
    if mode == "run":
        return edge.estimated_run_seconds
    if mode == "vehicle":
        return edge.estimated_vehicle_seconds
    return edge.estimated_walk_seconds


def camera_graph_to_dict(
    nodes: list[CameraGraphNode],
    edges: list[CameraGraphEdge],
) -> dict[str, Any]:
    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "edges": [e.model_dump(mode="json") for e in edges],
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
