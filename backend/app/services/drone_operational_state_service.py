"""Phase 8 — Drone Operational State Service.

Merges three existing subsystems into a single unified snapshot per drone:
  1. City surveillance registry (CityDrone) — base identity + status
  2. Scenario engine (ScenarioRun / DroneRoute) — dispatch + tracking context
  3. AirSim / CosysAirSim client — provider connectivity (optional, non-blocking)

AirSim is treated as an optional enhancement: if it is disconnected the
unified state still returns valid data with provider_status=disconnected.
This service is read-only; it does NOT mutate any subsystem state.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.models.drone_unified_models import (
    DroneMissionState,
    DroneProviderStatus,
    DroneRegistryStatus,
    DroneRoutePhase,
    ProviderState,
    UnifiedDroneState,
    UnifiedFleetState,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Registry status → unified enum
# ---------------------------------------------------------------------------

_REGISTRY_STATUS_MAP: dict[str, DroneRegistryStatus] = {
    "standby": DroneRegistryStatus.STANDBY,
    "airborne": DroneRegistryStatus.AIRBORNE,
    "returning": DroneRegistryStatus.RETURNING,
    "charging": DroneRegistryStatus.CHARGING,
    "offline": DroneRegistryStatus.OFFLINE,
    "mission": DroneRegistryStatus.MISSION,
}

_ROUTE_STATUS_MAP: dict[str, DroneRoutePhase] = {
    "planned": DroneRoutePhase.PLANNED,
    "dispatched": DroneRoutePhase.DISPATCHED,
    "tracking": DroneRoutePhase.TRACKING,
    "completed": DroneRoutePhase.COMPLETED,
    "cancelled": DroneRoutePhase.CANCELLED,
}


# ---------------------------------------------------------------------------
# AirSim provider check (non-blocking, returns safe defaults on failure)
# ---------------------------------------------------------------------------

def _get_provider_state() -> ProviderState:
    try:
        from app.services.drone.cosys_airsim_client import get_cosys_airsim_client
        client = get_cosys_airsim_client()
        health = client.get_health()
        if health.simulator_connected:
            status = DroneProviderStatus.CONNECTED
        elif health.status == "degraded":
            status = DroneProviderStatus.DEGRADED
        else:
            status = DroneProviderStatus.DISCONNECTED
        return ProviderState(
            provider=health.provider,
            status=status,
            simulator_connected=health.simulator_connected,
            telemetry_available=health.telemetry_available,
            frame_available=health.frame_available,
            last_error=health.last_error,
        )
    except Exception as exc:
        logger.debug("AirSim provider check failed (non-fatal): %s", exc)
        return ProviderState(
            status=DroneProviderStatus.DISCONNECTED,
            simulator_connected=False,
            last_error=str(exc),
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DroneOperationalStateService:
    """Read-only aggregator that merges registry + scenario + AirSim into
    UnifiedDroneState snapshots for each drone in the city registry."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_unified_fleet(self) -> UnifiedFleetState:
        """Return unified state for every drone in the city registry."""
        provider = _get_provider_state()
        drones = self._build_all_unified_states(provider)
        return UnifiedFleetState(
            drones=drones,
            total=len(drones),
            provider_connected=provider.simulator_connected,
            metadata={"provider": provider.model_dump(mode="json")},
        )

    def get_unified_drone(self, drone_id: str) -> UnifiedDroneState | None:
        """Return unified state for a single drone by ID."""
        provider = _get_provider_state()
        try:
            from app.services.simulation_source_service import get_city_surveillance_registry
            registry = get_city_surveillance_registry()
            drone_obj = registry.get_drone(drone_id)
            if drone_obj is None:
                return None
            return self._build_unified_state(drone_obj, provider)
        except Exception as exc:
            logger.warning("Failed to get unified drone state for %s: %s", drone_id, exc)
            return None

    def health(self) -> dict[str, Any]:
        return {"service": "drone_operational_state_service", "status": "ok"}

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_all_unified_states(self, provider: ProviderState) -> list[UnifiedDroneState]:
        try:
            from app.services.simulation_source_service import get_city_surveillance_registry
            registry = get_city_surveillance_registry()
            drones = registry.list_drones()
        except Exception as exc:
            logger.warning("Could not list drones from registry: %s", exc)
            return []
        return [self._build_unified_state(d, provider) for d in drones]

    def _build_unified_state(self, drone_obj: Any, provider: ProviderState) -> UnifiedDroneState:
        from app.services.scenario_engine_service import get_scenario_engine

        drone_id = drone_obj.drone_id
        registry_status = _REGISTRY_STATUS_MAP.get(
            str(drone_obj.status.value if hasattr(drone_obj.status, "value") else drone_obj.status),
            DroneRegistryStatus.STANDBY,
        )

        # Scenario engine state — dispatch + route
        active_scenario_run_id: str | None = None
        active_route_id: str | None = None
        route_status = DroneRoutePhase.NONE
        linked_actor_id: str | None = None
        dispatched_at: str | None = None

        try:
            engine = get_scenario_engine()
            run = engine.active_run()
            if run and run.drone_dispatched and run.dispatched_drone_id == drone_id:
                active_scenario_run_id = run.run_id
                dispatched_at = run.started_at
                route = engine.get_drone_route(run.run_id)
                if route:
                    active_route_id = route.route_id
                    route_status = _ROUTE_STATUS_MAP.get(
                        route.status.value if hasattr(route.status, "value") else str(route.status),
                        DroneRoutePhase.NONE,
                    )
                    linked_actor_id = route.linked_actor_id
        except Exception as exc:
            logger.debug("Scenario state lookup for %s failed: %s", drone_id, exc)

        # Mission layer — check CityDrone.mission_id and try to load session
        active_mission_id: str | None = getattr(drone_obj, "mission_id", None)
        mission_status: str | None = None
        mission_state: DroneMissionState | None = None

        if active_mission_id:
            mission_state, mission_status = self._load_mission_state(active_mission_id)

        return UnifiedDroneState(
            drone_id=drone_id,
            name=drone_obj.name,
            simulated=True,
            registry_status=registry_status,
            assigned_zone=drone_obj.assigned_zone,
            battery_percent=float(drone_obj.battery_percent),
            current_location=drone_obj.current_location.model_dump(mode="json")
                if hasattr(drone_obj.current_location, "model_dump")
                else (drone_obj.current_location or {}),
            home_location=drone_obj.home_location.model_dump(mode="json")
                if hasattr(drone_obj.home_location, "model_dump")
                else (drone_obj.home_location or {}),
            camera_feed_uri=drone_obj.camera_feed_uri or "",
            capabilities=list(drone_obj.capabilities or []),
            active_mission_id=active_mission_id,
            mission_status=mission_status,
            mission_state=mission_state,
            active_scenario_run_id=active_scenario_run_id,
            active_route_id=active_route_id,
            route_status=route_status,
            linked_actor_id=linked_actor_id,
            dispatched_at=dispatched_at,
            provider_status=provider.status,
            provider_state=provider,
            telemetry_source="registry",
            last_updated_at=_now_iso(),
            metadata={
                "simulated": True,
                "scenario_dispatched": active_scenario_run_id is not None,
            },
        )

    def _load_mission_state(self, mission_id: str) -> tuple[DroneMissionState | None, str | None]:
        """Try to load an active mission session from the mission repository."""
        try:
            from app.repositories.drone_mission_repository import DroneMissionRepository
            repo = DroneMissionRepository()
            session = repo.get_active_session_for_mission(mission_id)
            if session:
                return (
                    DroneMissionState(
                        mission_id=mission_id,
                        mission_name=getattr(session, "mission_name", "Simulated Aerial Patrol Mission"),
                        mission_status=session.status.value if hasattr(session.status, "value") else str(session.status),
                        current_waypoint_index=session.current_waypoint_index,
                        progress_percent=session.progress_percent,
                        started_at=session.started_at,
                    ),
                    session.status.value if hasattr(session.status, "value") else str(session.status),
                )
        except Exception as exc:
            logger.debug("Mission state load for %s failed (non-fatal): %s", mission_id, exc)
        return None, None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_svc: DroneOperationalStateService | None = None
_svc_lock = threading.Lock()


def get_drone_operational_state_service() -> DroneOperationalStateService:
    global _svc
    if _svc is None:
        with _svc_lock:
            if _svc is None:
                _svc = DroneOperationalStateService()
    return _svc
