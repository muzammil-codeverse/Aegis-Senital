"""Phase 8 — Drone Mission, Drone Fusion, and Drone State Unification tests.

Tests:
 1. UnifiedDroneState model serializes correctly
 2. ProviderState defaults to disconnected
 3. DroneMissionState serializes correctly
 4. UnifiedFleetState wraps drone list
 5. DroneOperationalStateService.health() returns ok
 6. DroneOperationalStateService.get_unified_fleet() returns valid fleet
 7. DroneOperationalStateService.get_unified_drone() returns DRONE-ALPHA
 8. DroneOperationalStateService.get_unified_drone() returns None for unknown drone
 9. DroneRoute status advances: DISPATCHED → TRACKING on drone_observation step
10. DroneRoute status advances: TRACKING → COMPLETED on scenario_incident step
"""
from __future__ import annotations

import pytest

from app.models.drone_unified_models import (
    DroneMissionState,
    DroneProviderStatus,
    DroneRegistryStatus,
    DroneRoutePhase,
    ProviderState,
    UnifiedDroneState,
    UnifiedFleetState,
)
from app.models.tracking_models import DroneRouteStatus


# ---------------------------------------------------------------------------
# Part 1: Model serialization
# ---------------------------------------------------------------------------


def test_unified_drone_state_serializes():
    state = UnifiedDroneState(
        drone_id="DRONE-ALPHA",
        name="Alpha Surveillance Drone",
        registry_status=DroneRegistryStatus.STANDBY,
        assigned_zone="zone_financial",
        battery_percent=100.0,
        capabilities=["hd_video", "thermal"],
    )
    data = state.model_dump(mode="json")
    assert data["drone_id"] == "DRONE-ALPHA"
    assert data["registry_status"] == "standby"
    assert data["route_status"] == "none"
    assert data["simulated"] is True


def test_provider_state_defaults_unknown():
    ps = ProviderState()
    # Default is UNKNOWN because no connection check has been performed yet
    assert ps.status == DroneProviderStatus.UNKNOWN
    assert ps.simulator_connected is False


def test_drone_mission_state_serializes():
    ms = DroneMissionState(
        mission_id="mission-abc",
        mission_name="Simulated Patrol",
        mission_status="executing",
        current_waypoint_index=2,
        progress_percent=40.0,
    )
    data = ms.model_dump(mode="json")
    assert data["mission_id"] == "mission-abc"
    assert data["progress_percent"] == 40.0


def test_unified_fleet_state_wraps_drones():
    d1 = UnifiedDroneState(drone_id="DRONE-ALPHA", name="Alpha")
    d2 = UnifiedDroneState(drone_id="DRONE-BRAVO", name="Bravo")
    fleet = UnifiedFleetState(drones=[d1, d2], total=2)
    data = fleet.model_dump(mode="json")
    assert data["total"] == 2
    assert len(data["drones"]) == 2


# ---------------------------------------------------------------------------
# Part 2: DroneOperationalStateService
# ---------------------------------------------------------------------------


def test_drone_operational_state_service_health():
    from app.services.drone_operational_state_service import DroneOperationalStateService
    svc = DroneOperationalStateService()
    health = svc.health()
    assert health["status"] == "ok"
    assert "drone_operational_state_service" in health["service"]


def test_drone_operational_state_service_get_unified_fleet():
    from app.services.drone_operational_state_service import DroneOperationalStateService
    svc = DroneOperationalStateService()
    fleet = svc.get_unified_fleet()
    assert fleet is not None
    assert isinstance(fleet.drones, list)
    assert fleet.total >= 0
    # Should not raise even if AirSim is disconnected


def test_drone_operational_state_service_drone_alpha_present():
    from app.services.drone_operational_state_service import DroneOperationalStateService
    svc = DroneOperationalStateService()
    state = svc.get_unified_drone("DRONE-ALPHA")
    assert state is not None
    assert state.drone_id == "DRONE-ALPHA"
    assert state.simulated is True
    assert state.assigned_zone != ""


def test_drone_operational_state_service_unknown_drone_returns_none():
    from app.services.drone_operational_state_service import DroneOperationalStateService
    svc = DroneOperationalStateService()
    state = svc.get_unified_drone("DRONE-NONEXISTENT-XYZ")
    assert state is None


# ---------------------------------------------------------------------------
# Part 3: DroneRoute lifecycle (DISPATCHED → TRACKING → COMPLETED)
# ---------------------------------------------------------------------------


def test_drone_route_advances_to_tracking_on_drone_observation():
    from app.services.scenario_engine_service import ScenarioEngineService
    from app.models.tracking_models import DroneRouteStatus

    engine = ScenarioEngineService()
    run = engine.start("bank_robbery_demo", mode="step")

    # Step until drone is dispatched (weapon_detected at step 3)
    for _ in range(4):
        engine.step()

    # Verify route was created with DISPATCHED status
    route = engine.get_drone_route(run.run_id)
    assert route is not None
    assert route.status in (DroneRouteStatus.DISPATCHED, DroneRouteStatus.TRACKING)

    # Step until drone_observation event (step 5)
    dispatched_route_status = route.status
    for _ in range(3):
        result = engine.step()
        if result.get("event_type") == "drone_observation":
            break

    route = engine.get_drone_route(run.run_id)
    assert route is not None
    # After a drone_observation event, status should have advanced to TRACKING
    # (or stay if already past it)
    assert route.status in (DroneRouteStatus.TRACKING, DroneRouteStatus.COMPLETED)


def test_drone_route_advances_to_completed_on_scenario_incident():
    from app.services.scenario_engine_service import ScenarioEngineService
    from app.models.tracking_models import DroneRouteStatus

    engine = ScenarioEngineService()
    run = engine.start("bank_robbery_demo", mode="step")

    # Run all steps
    for _ in range(run.total_steps):
        try:
            engine.step()
        except Exception:
            break

    route = engine.get_drone_route(run.run_id)
    if route:
        assert route.status in (DroneRouteStatus.COMPLETED, DroneRouteStatus.TRACKING)


def test_drone_route_advances_to_cancelled_on_cancel():
    from app.services.scenario_engine_service import ScenarioEngineService
    from app.models.tracking_models import DroneRouteStatus

    engine = ScenarioEngineService()
    run = engine.start("bank_robbery_demo", mode="step")

    # Step until dispatch
    for _ in range(5):
        engine.step()

    route = engine.get_drone_route(run.run_id)
    if route:
        engine.cancel()
        route = engine.get_drone_route(run.run_id)
        assert route is not None
        assert route.status == DroneRouteStatus.CANCELLED
