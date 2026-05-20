"""Phase 7 — Tracking, path, fused-track, drone route, and API tests."""
from __future__ import annotations

import pytest

from app.models.tracking_models import (
    CameraHandoff,
    DroneRoute,
    DroneRouteStatus,
    EntityType,
    FusedTrack,
    FusedTrackStatus,
    PathWaypoint,
    WaypointLocation,
)
from app.services.scenario_engine_service import (
    BANK_ROBBERY_CAMERA_HANDOFFS,
    BANK_ROBBERY_DEMO,
    BANK_ROBBERY_SUSPECT_PATH,
    DRONE_ALPHA_ROUTE_WAYPOINTS,
    SCENARIO_CATALOGUE,
    ScenarioEngineService,
)
from app.services.fused_path_service import FusedPathService


# ---------------------------------------------------------------------------
# Part 1: Suspect path exists for bank_robbery_demo
# ---------------------------------------------------------------------------


def test_suspect_path_exists_for_bank_robbery():
    assert len(BANK_ROBBERY_SUSPECT_PATH) >= 5


def test_suspect_path_all_belong_to_suspect_001():
    for raw in BANK_ROBBERY_SUSPECT_PATH:
        assert raw["entity_id"] == "SUSPECT-001"
        assert raw["entity_type"] == "suspect"


def test_suspect_path_has_increasing_offsets():
    offsets = [raw["offset_seconds"] for raw in BANK_ROBBERY_SUSPECT_PATH]
    assert offsets == sorted(offsets)


# ---------------------------------------------------------------------------
# Part 2: All suspect path camera/source references are valid
# ---------------------------------------------------------------------------


def test_suspect_path_camera_refs_in_scenario_cameras():
    scenario_cameras = set(BANK_ROBBERY_DEMO.camera_ids)
    for raw in BANK_ROBBERY_SUSPECT_PATH:
        src = raw.get("source_id")
        if src:
            assert src in scenario_cameras, f"{src} not in scenario camera list"


# ---------------------------------------------------------------------------
# Part 3: Camera handoff chain exists and references registered cameras
# ---------------------------------------------------------------------------


def test_camera_handoff_chain_exists():
    assert len(BANK_ROBBERY_CAMERA_HANDOFFS) >= 5


def test_camera_handoff_chain_actor_is_suspect():
    for raw in BANK_ROBBERY_CAMERA_HANDOFFS:
        assert raw["actor_id"] == "SUSPECT-001"


def test_camera_handoff_chain_cameras_are_registered():
    from app.services.simulation_source_service import get_city_surveillance_registry
    registry = get_city_surveillance_registry()
    valid_ids = {c.camera_id for c in registry.list_cameras()}
    for raw in BANK_ROBBERY_CAMERA_HANDOFFS:
        assert raw["from_camera_id"] in valid_ids, f"{raw['from_camera_id']} not registered"
        assert raw["to_camera_id"] in valid_ids, f"{raw['to_camera_id']} not registered"


def test_camera_handoff_forms_a_chain():
    pairs = [(raw["from_camera_id"], raw["to_camera_id"]) for raw in BANK_ROBBERY_CAMERA_HANDOFFS]
    for i in range(1, len(pairs)):
        assert pairs[i][0] == pairs[i - 1][1], (
            f"Handoff {i}: from_camera {pairs[i][0]} != previous to_camera {pairs[i - 1][1]}"
        )


# ---------------------------------------------------------------------------
# Part 4: DRONE-ALPHA route is created after dispatch step
# ---------------------------------------------------------------------------


def test_drone_alpha_route_template_exists():
    assert len(DRONE_ALPHA_ROUTE_WAYPOINTS) >= 4


def test_drone_alpha_route_references_drone_alpha():
    entity_ids = {raw["entity_id"] for raw in DRONE_ALPHA_ROUTE_WAYPOINTS}
    assert "DRONE-ALPHA" in entity_ids


def test_drone_route_created_after_dispatch():
    engine = ScenarioEngineService()
    run = engine.start("bank_robbery_demo", mode="step")
    # Step through until drone dispatch (step 5, trigger at step 3)
    for _ in range(6):
        result = engine.step()
        if result.get("run_status", {}).get("drone_dispatched"):
            break
    route = engine.get_drone_route(run.run_id)
    assert route is not None
    assert route.drone_id == "DRONE-ALPHA"
    assert len(route.waypoints) >= 4
    assert route.status in (DroneRouteStatus.DISPATCHED, DroneRouteStatus.TRACKING)
    assert route.linked_actor_id == "SUSPECT-001"


# ---------------------------------------------------------------------------
# Part 5: Fused track includes camera observations
# ---------------------------------------------------------------------------


def test_fused_track_includes_camera_observations():
    engine = ScenarioEngineService()
    run = engine.start("bank_robbery_demo", mode="step")
    for _ in range(4):
        engine.step()
    track = engine.get_fused_track(run.run_id)
    assert track is not None
    assert len(track.camera_observations) > 0


# ---------------------------------------------------------------------------
# Part 6: Fused track includes drone observations after drone event
# ---------------------------------------------------------------------------


def test_fused_track_includes_drone_observations_after_drone_event():
    engine = ScenarioEngineService()
    run = engine.start("bank_robbery_demo", mode="step")
    # Step to at least the drone_observation event (step 5)
    for _ in range(7):
        engine.step()
    track = engine.get_fused_track(run.run_id)
    assert track is not None
    assert "drone_camera" in track.source_types or len(track.drone_observations) > 0


# ---------------------------------------------------------------------------
# Part 7: FusedPathService returns valid operational-view shape
# ---------------------------------------------------------------------------


def test_fused_path_service_returns_suspect_path():
    from app.services.scenario_engine_service import get_scenario_engine
    engine = get_scenario_engine()
    engine.reset()
    run = engine.start("bank_robbery_demo", mode="step")
    svc = FusedPathService()
    path = svc.get_suspect_path(run.run_id)
    assert len(path) >= 5
    assert all(isinstance(w, PathWaypoint) for w in path)
    engine.reset()


def test_fused_path_service_get_camera_handoffs_all_valid():
    from app.services.scenario_engine_service import get_scenario_engine
    engine = get_scenario_engine()
    engine.reset()
    run = engine.start("bank_robbery_demo", mode="step")
    svc = FusedPathService()
    handoffs = svc.get_camera_handoffs(run.run_id)
    assert len(handoffs) >= 5
    for h in handoffs:
        assert isinstance(h, CameraHandoff)
    engine.reset()


# ---------------------------------------------------------------------------
# Part 8: Invalid run returns clean error shape
# ---------------------------------------------------------------------------


def test_get_suspect_path_unknown_run_returns_empty():
    engine = ScenarioEngineService()
    path = engine.get_suspect_path("nonexistent-run-id")
    assert path == []


def test_get_drone_route_unknown_run_returns_none():
    engine = ScenarioEngineService()
    route = engine.get_drone_route("nonexistent-run-id")
    assert route is None


def test_get_fused_track_unknown_run_returns_none():
    engine = ScenarioEngineService()
    track = engine.get_fused_track("nonexistent-run-id")
    assert track is None


# ---------------------------------------------------------------------------
# Part 9: Alert metadata includes scenario_run_id and tracking context
# ---------------------------------------------------------------------------


def test_alert_metadata_includes_tracking_context():
    engine = ScenarioEngineService()
    run = engine.start("bank_robbery_demo", mode="step")
    # Step to weapon_detected (step 3)
    for _ in range(4):
        engine.step()
    promotions = engine.list_promotions(run.run_id)
    weapon_promos = [p for p in promotions if p.get("event_type") == "weapon_detected"]
    assert len(weapon_promos) > 0
    alert = weapon_promos[0].get("alert", {})
    meta = alert.get("metadata", {})
    assert meta.get("run_id") == run.run_id
    assert meta.get("scenario_id") == "bank_robbery_demo"
    assert meta.get("has_tracking_view") is True
    assert meta.get("tracking_view") is not None


# ---------------------------------------------------------------------------
# Part 10: Tracking domain models serialize correctly
# ---------------------------------------------------------------------------


def test_path_waypoint_serializes():
    wp = PathWaypoint(
        waypoint_id="wp-test-01",
        entity_id="SUSPECT-001",
        entity_type=EntityType.SUSPECT,
        offset_seconds=15,
        location=WaypointLocation(x=145.0, y=100.0, z=3.0),
        zone_id="zone_financial",
        zone_name="Financial District",
        source_id="CAM-BANK-02",
        source_type="fixed_cctv",
        confidence=0.95,
    )
    data = wp.model_dump(mode="json")
    assert data["entity_type"] == "suspect"
    assert data["location"]["x"] == 145.0
    assert data["confidence"] == 0.95


def test_camera_handoff_serializes():
    h = CameraHandoff(
        handoff_id="hoff-01",
        scenario_run_id="run-test",
        from_camera_id="CAM-BANK-01",
        to_camera_id="CAM-BANK-02",
        actor_id="SUSPECT-001",
        offset_seconds=15,
        reason="weapon_detected",
        confidence=0.95,
    )
    data = h.model_dump(mode="json")
    assert data["from_camera_id"] == "CAM-BANK-01"
    assert data["to_camera_id"] == "CAM-BANK-02"


def test_fused_track_serializes():
    ft = FusedTrack(
        track_id="ftrack-test",
        scenario_run_id="run-test",
        actor_id="SUSPECT-001",
        source_types=["scenario_observation", "drone_camera"],
        status=FusedTrackStatus.ACTIVE,
        confidence=0.88,
    )
    data = ft.model_dump(mode="json")
    assert data["status"] == "active"
    assert "drone_camera" in data["source_types"]


def test_drone_route_serializes():
    route = DroneRoute(
        route_id="route-test",
        scenario_run_id="run-test",
        drone_id="DRONE-ALPHA",
        status=DroneRouteStatus.DISPATCHED,
        linked_actor_id="SUSPECT-001",
    )
    data = route.model_dump(mode="json")
    assert data["drone_id"] == "DRONE-ALPHA"
    assert data["status"] == "dispatched"
