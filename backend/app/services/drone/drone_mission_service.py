"""Mission planning service for simulated drone patrol missions (Phase 45).

Handles validation, route estimation, and mission lifecycle management.
All missions are simulated-only; no real-world deployment is implied.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.drone_mission_models import (
    DroneMissionCreateRequest,
    DroneMissionPlan,
    DroneMissionRoutePreview,
    DroneMissionStatus,
    DroneWaypoint,
)
from app.repositories.drone_mission_repository import (
    DroneMissionRepository,
    get_drone_mission_repository,
)
from app.services.drone.drone_coordinate_mapper import haversine_distance_meters
from inference.config_runtime import load_runtime_config


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_mission_config() -> dict[str, Any]:
    """Load drone_mission runtime configuration."""
    try:
        cfg = load_runtime_config("drone_mission")
        return dict(cfg.get("drone_mission") or {})
    except Exception:
        return {}


class ValidationError(Exception):
    """Raised when a mission plan fails validation."""


class DroneMissionService:
    """Planning and CRUD service for simulated drone patrol missions."""

    def __init__(self, repository: DroneMissionRepository | None = None) -> None:
        self._repo = repository or get_drone_mission_repository()
        self._config = _load_mission_config()
        self._mission_cfg = dict(self._config.get("mission") or {})

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    @property
    def max_waypoints(self) -> int:
        return int(self._mission_cfg.get("max_waypoints", 50))

    @property
    def min_waypoints(self) -> int:
        return int(self._mission_cfg.get("min_waypoints", 2))

    @property
    def default_altitude(self) -> float:
        return float(self._mission_cfg.get("default_altitude_meters", 40.0))

    @property
    def default_velocity(self) -> float:
        return float(self._mission_cfg.get("default_velocity_mps", 5.0))

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_mission_plan(self, waypoints: list[DroneWaypoint]) -> None:
        """Validate waypoint list for a mission plan.

        Raises ValidationError with a descriptive message on failure.
        """
        n = len(waypoints)
        if n < self.min_waypoints:
            raise ValidationError(
                f"Mission requires at least {self.min_waypoints} waypoints; got {n}"
            )
        if n > self.max_waypoints:
            raise ValidationError(
                f"Mission exceeds maximum of {self.max_waypoints} waypoints; got {n}"
            )
        for i, wp in enumerate(waypoints):
            if not (-90.0 <= wp.latitude <= 90.0):
                raise ValidationError(f"Waypoint {i}: invalid latitude {wp.latitude}")
            if not (-180.0 <= wp.longitude <= 180.0):
                raise ValidationError(f"Waypoint {i}: invalid longitude {wp.longitude}")
            if wp.altitude_meters <= 0:
                raise ValidationError(
                    f"Waypoint {i}: altitude_meters must be > 0 (got {wp.altitude_meters})"
                )
            if wp.velocity_mps <= 0:
                raise ValidationError(
                    f"Waypoint {i}: velocity_mps must be > 0 (got {wp.velocity_mps})"
                )

    # ------------------------------------------------------------------
    # Route estimation
    # ------------------------------------------------------------------

    def estimate_route(
        self,
        waypoints: list[DroneWaypoint],
    ) -> dict[str, float]:
        """Estimate total distance and duration for a waypoint sequence.

        Uses haversine distance between consecutive waypoints and the
        per-waypoint velocity to produce a time estimate.

        Returns:
            dict with keys 'distance_meters' and 'duration_seconds'.
        """
        total_dist = 0.0
        total_time = 0.0
        for i in range(len(waypoints) - 1):
            wp_a = waypoints[i]
            wp_b = waypoints[i + 1]
            dist = haversine_distance_meters(
                wp_a.latitude, wp_a.longitude,
                wp_b.latitude, wp_b.longitude,
            )
            avg_velocity = (wp_a.velocity_mps + wp_b.velocity_mps) / 2.0
            segment_time = dist / max(avg_velocity, 0.1)
            total_dist += dist
            total_time += segment_time
            total_time += float(wp_a.hold_seconds)

        # Add hold time at final waypoint
        if waypoints:
            total_time += float(waypoints[-1].hold_seconds)

        return {
            "distance_meters": round(total_dist, 2),
            "duration_seconds": round(total_time, 2),
        }

    # ------------------------------------------------------------------
    # Mission CRUD
    # ------------------------------------------------------------------

    def create_mission(
        self,
        request: DroneMissionCreateRequest,
        created_by: str | None = None,
    ) -> DroneMissionPlan:
        """Validate, estimate, and persist a new simulated patrol mission."""
        self.validate_mission_plan(request.waypoints)

        # Apply default altitude/velocity if not set per waypoint
        waypoints = []
        for idx, wp in enumerate(request.waypoints):
            waypoints.append(
                wp.model_copy(
                    update={
                        "sequence_index": idx,
                        "altitude_meters": wp.altitude_meters or self.default_altitude,
                        "velocity_mps": wp.velocity_mps or self.default_velocity,
                    }
                )
            )

        estimates = self.estimate_route(waypoints)
        mission = DroneMissionPlan(
            name=request.name,
            description=request.description,
            route_type=request.route_type,
            waypoints=waypoints,
            assigned_drone_id=request.assigned_drone_id,
            created_by=created_by,
            status=DroneMissionStatus.DRAFT,
            estimated_distance_meters=estimates["distance_meters"],
            estimated_duration_seconds=estimates["duration_seconds"],
            metadata=request.metadata,
        )
        return self._repo.create_mission(mission)

    def update_mission(
        self,
        mission_id: str,
        updates: dict[str, Any],
    ) -> DroneMissionPlan | None:
        """Apply *updates* to an existing mission plan."""
        return self._repo.update_mission(mission_id, updates)

    def get_mission(self, mission_id: str) -> DroneMissionPlan | None:
        """Return a mission plan by ID."""
        return self._repo.get_mission(mission_id)

    def list_missions(
        self,
        status: DroneMissionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DroneMissionPlan]:
        """Return missions, optionally filtered by status."""
        return self._repo.list_missions(status=status, limit=limit, offset=offset)

    def delete_mission(self, mission_id: str) -> bool:
        """Delete a mission plan. Only DRAFT missions may be deleted."""
        mission = self._repo.get_mission(mission_id)
        if mission is None:
            return False
        if mission.status not in (DroneMissionStatus.DRAFT, DroneMissionStatus.CANCELLED):
            raise ValidationError(
                f"Cannot delete mission in status '{mission.status.value}'"
            )
        return self._repo.delete_mission(mission_id)

    # ------------------------------------------------------------------
    # Route preview
    # ------------------------------------------------------------------

    def generate_route_preview(
        self,
        mission_id: str,
    ) -> DroneMissionRoutePreview | None:
        """Generate a GIS-friendly route preview for a mission."""
        mission = self._repo.get_mission(mission_id)
        if mission is None:
            return None
        estimates = self.estimate_route(mission.waypoints)
        return DroneMissionRoutePreview(
            mission_id=mission.mission_id,
            route_type=mission.route_type,
            waypoints=mission.waypoints,
            estimated_distance_meters=estimates["distance_meters"],
            estimated_duration_seconds=estimates["duration_seconds"],
        )

    # ------------------------------------------------------------------
    # Mission report generation (planning-side summary)
    # ------------------------------------------------------------------

    def generate_mission_report_stub(
        self,
        mission_id: str,
    ) -> dict[str, Any]:
        """Return a planning-level report stub (no session data)."""
        mission = self._repo.get_mission(mission_id)
        if mission is None:
            return {"status": "error", "detail": "Mission not found"}
        return {
            "mission_id": mission.mission_id,
            "name": mission.name,
            "status": mission.status.value,
            "simulated": True,
            "operator_review_required": True,
            "waypoint_count": len(mission.waypoints),
            "estimated_distance_meters": mission.estimated_distance_meters,
            "estimated_duration_seconds": mission.estimated_duration_seconds,
            "safe_label": mission.safe_label,
            "generated_at": _now_iso(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: DroneMissionService | None = None
_service_lock = threading.Lock()


def get_drone_mission_service() -> DroneMissionService:
    """Return the process-wide DroneMissionService singleton."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = DroneMissionService()
    return _service
