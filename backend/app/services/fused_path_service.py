from __future__ import annotations

import logging
import threading
from typing import Any

from app.models.tracking_models import CameraHandoff, DroneRoute, FusedTrack, PathWaypoint

logger = logging.getLogger(__name__)


class FusedPathService:
    """Deterministic scenario-level fused tracking service.

    Combines CCTV observations, drone observations, suspect path waypoints,
    drone route waypoints, and camera handoffs into a unified FusedTrack.
    Source of truth is the ScenarioEngineService singleton; this service
    is a façade that validates source IDs and presents clean outputs.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_fused_track(self, run_id: str) -> FusedTrack | None:
        from app.services.scenario_engine_service import get_scenario_engine
        engine = get_scenario_engine()
        return engine.get_fused_track(run_id)

    def get_suspect_path(self, run_id: str) -> list[PathWaypoint]:
        from app.services.scenario_engine_service import get_scenario_engine
        engine = get_scenario_engine()
        return engine.get_suspect_path(run_id)

    def get_camera_handoffs(self, run_id: str) -> list[CameraHandoff]:
        from app.services.scenario_engine_service import get_scenario_engine
        engine = get_scenario_engine()
        handoffs = engine.get_camera_handoffs(run_id)
        valid = self._validate_handoff_cameras(handoffs)
        return valid

    def get_drone_route(self, run_id: str) -> DroneRoute | None:
        from app.services.scenario_engine_service import get_scenario_engine
        engine = get_scenario_engine()
        return engine.get_drone_route(run_id)

    def get_operational_view(self, run_id: str) -> dict[str, Any] | None:
        """Combined operational view for the frontend — single call covers all tracking data."""
        from app.services.scenario_engine_service import get_scenario_engine
        engine = get_scenario_engine()

        run = engine.active_run()
        if run is None or run.run_id != run_id:
            return None

        suspect_path = engine.get_suspect_path(run_id)
        handoffs = self.get_camera_handoffs(run_id)
        drone_route = engine.get_drone_route(run_id)
        fused_track = engine.get_fused_track(run_id)

        promotions = engine.list_promotions(run_id)
        alerts = [p["alert"] for p in promotions if p.get("alert")]
        incidents = [p["incident"] for p in promotions if p.get("incident")]

        involved_cameras: list[str] = list(dict.fromkeys(
            wp.source_id for wp in suspect_path if wp.source_id
        ))
        involved_drones = [run.dispatched_drone_id] if run.drone_dispatched and run.dispatched_drone_id else []

        current_event: dict[str, Any] | None = None
        if run.observation_timeline:
            latest = run.observation_timeline[-1]
            current_event = {
                "step": latest.get("step"),
                "t_offset_seconds": latest.get("t_offset_seconds"),
                "event_type": latest.get("event_type"),
                "observation": latest.get("observation", {}),
            }

        return {
            "run_id": run_id,
            "scenario_id": run.scenario_id,
            "scenario_name": run.scenario_name,
            "state": run.state.value,
            "current_step": run.current_step,
            "total_steps": run.total_steps,
            "drone_dispatched": run.drone_dispatched,
            "dispatched_drone_id": run.dispatched_drone_id,
            "current_event": current_event,
            "suspect_path": [w.model_dump(mode="json") for w in suspect_path],
            "camera_handoffs": [h.model_dump(mode="json") for h in handoffs],
            "drone_route": drone_route.model_dump(mode="json") if drone_route else None,
            "fused_track": fused_track.model_dump(mode="json") if fused_track else None,
            "alerts": alerts,
            "incidents": incidents,
            "involved_cameras": involved_cameras,
            "involved_drones": involved_drones,
        }

    # ------------------------------------------------------------------
    # Internal validation
    # ------------------------------------------------------------------

    def _validate_handoff_cameras(self, handoffs: list[CameraHandoff]) -> list[CameraHandoff]:
        """Filter out any handoff referencing an unregistered camera."""
        try:
            from app.services.simulation_source_service import get_city_surveillance_registry
            registry = get_city_surveillance_registry()
            valid_ids = {c.camera_id for c in registry.list_cameras()}
        except Exception:
            return handoffs
        validated: list[CameraHandoff] = []
        for h in handoffs:
            if h.from_camera_id in valid_ids and h.to_camera_id in valid_ids:
                validated.append(h)
            else:
                logger.warning(
                    "Camera handoff %s references unregistered camera(s): %s → %s",
                    h.handoff_id, h.from_camera_id, h.to_camera_id,
                )
        return validated

    def health(self) -> dict[str, Any]:
        return {
            "service": "fused_path_service",
            "status": "ok",
            "description": "Deterministic scenario-level fused tracking façade.",
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: FusedPathService | None = None
_service_lock = threading.Lock()


def get_fused_path_service() -> FusedPathService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = FusedPathService()
    return _service
