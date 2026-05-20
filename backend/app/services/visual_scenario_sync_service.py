"""
Phase XII — Visual Scenario Sync Service.

Connects the ScenarioEngineService timeline to the AegisVisualScenarioController
so that the AirSim visual world advances in lock-step with backend scenario
steps. This is the bridge that turns the static dashboard demo into a
visually driven simulation.

Responsibilities
----------------
* When the exhibition demo starts, build the visual scene (zones, camera
  markers, actors, drone route, crime marker outlines) and kick off the
  animation thread.
* Each time the demo steps, push the new t_offset_seconds to the visual
  controller and (best-effort) capture a fresh snapshot of the active
  camera.
* On stop/reset, cancel the animation, flush markers, and clear snapshots.
* Expose a snapshot directory and per-camera status that the dashboard
  can poll without holding the AirSim client lock.

Public API
----------
sync_to_scenario_run(run_status)
    Push the current ScenarioRunStatus into the visual world.

handle_step(step_payload)
    Take the dict returned by ScenarioEngineService.step() and advance the
    visual clock to its t_offset_seconds. Captures a snapshot of the
    step's camera if AirSim is available.

start_for_demo()
    Build the static scene and start animation when the demo begins.

stop_for_demo()
    Stop animation and (optionally) flush markers.

get_status()
    Return aggregate visual sync state for the dashboard.

list_camera_status()
    Return per-camera snapshot/sync state for the dashboard camera cards.

The service degrades gracefully when AirSim is unreachable: every entry
point returns a structured status dict rather than raising.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SNAPSHOT_DIR = _PROJECT_ROOT / "runtime_state" / "visual_snapshots"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VisualScenarioSyncService:
    """Coordinates visuals with the scenario engine timeline."""

    def __init__(
        self,
        *,
        controller_factory=None,
        snapshot_dir: Path | str | None = None,
        auto_capture_snapshots: bool = True,
    ) -> None:
        if controller_factory is None:
            from app.services.visual_scenario_controller import (
                get_visual_scenario_controller,
            )
            controller_factory = get_visual_scenario_controller
        self._controller_factory = controller_factory
        self._snapshot_dir = Path(snapshot_dir or _SNAPSHOT_DIR)
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._auto_snapshots = bool(auto_capture_snapshots)
        self._lock = threading.RLock()
        self._scenario_run_id: str | None = None
        self._last_step_payload: dict[str, Any] | None = None
        self._last_sync_at: str | None = None
        self._last_t_offset: float | None = None
        self._last_error: str | None = None
        self._active: bool = False
        self._camera_status: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Lifecycle entry points
    # ------------------------------------------------------------------

    def start_for_demo(
        self, *, scenario_run_id: str | None = None, duration: float = 65.0
    ) -> dict[str, Any]:
        """Build the visual scene and start animation for the demo run."""
        with self._lock:
            ctrl = self._controller_factory()
            setup_result = ctrl.setup_static_scene()
            try:
                ctrl.start_animation_thread(duration=duration)
            except Exception as exc:
                logger.warning("[VisualSync] start_animation failed: %s", exc)
                setup_result.setdefault("animation_error", str(exc))
            self._scenario_run_id = scenario_run_id
            self._active = True
            self._last_sync_at = _now_iso()
            self._last_error = setup_result.get("error")
            logger.info(
                "[VisualSync] Visual demo started (run=%s, mode=%s)",
                scenario_run_id, setup_result.get("real_actor_mode"),
            )
            return {
                "status": "ok",
                "scenario_run_id": scenario_run_id,
                "setup": setup_result,
                "controller": ctrl.get_status(),
                "snapshot_dir": str(self._snapshot_dir),
            }

    def stop_for_demo(self, *, flush_markers: bool = False) -> dict[str, Any]:
        with self._lock:
            ctrl = self._controller_factory()
            try:
                ctrl.stop_animation()
            except Exception as exc:
                logger.warning("[VisualSync] stop_animation failed: %s", exc)
            if flush_markers:
                try:
                    ctrl.flush_markers()
                except Exception as exc:
                    logger.warning("[VisualSync] flush_markers failed: %s", exc)
            self._active = False
            logger.info("[VisualSync] Visual demo stopped (flush=%s)", flush_markers)
            return {
                "status": "ok",
                "flushed": flush_markers,
                "controller": ctrl.get_status(),
            }

    # ------------------------------------------------------------------
    # Sync entry points
    # ------------------------------------------------------------------

    def sync_to_offset(
        self,
        t_offset_seconds: float,
        *,
        camera_id: str | None = None,
        capture_snapshot: bool | None = None,
    ) -> dict[str, Any]:
        """Push the visual clock to a specific scenario time."""
        with self._lock:
            ctrl = self._controller_factory()
            sync_result = ctrl.sync_to_offset(float(t_offset_seconds))
            self._last_t_offset = float(t_offset_seconds)
            self._last_sync_at = _now_iso()
            self._last_error = sync_result.get("error")

            snapshot_result: dict[str, Any] | None = None
            should_capture = (
                self._auto_snapshots if capture_snapshot is None else bool(capture_snapshot)
            )
            if should_capture and camera_id:
                snapshot_result = ctrl.capture_camera_snapshot(camera_id)
                if snapshot_result.get("status") == "ok":
                    self._record_camera_status(camera_id, snapshot_result)

            return {
                "status": sync_result.get("status", "ok"),
                "t_offset_seconds": float(t_offset_seconds),
                "camera_id": camera_id,
                "snapshot": snapshot_result,
                "sync": sync_result,
            }

    def handle_step(self, step_payload: dict[str, Any] | None) -> dict[str, Any]:
        """
        Receive a payload from ScenarioEngineService.step() and advance
        the visual world to its t_offset_seconds. Captures a snapshot
        for the step's camera when auto_snapshots is on.
        """
        if not isinstance(step_payload, dict):
            return {"status": "skipped", "reason": "no step payload"}

        with self._lock:
            self._last_step_payload = dict(step_payload)
            t_offset = float(step_payload.get("t_offset_seconds") or 0.0)
            obs = step_payload.get("observation") or {}
            camera_id = (
                obs.get("camera_id")
                if isinstance(obs, dict)
                else None
            )
            result = self.sync_to_offset(t_offset, camera_id=camera_id)
            result["step"] = step_payload.get("step")
            result["event_type"] = step_payload.get("event_type")
            return result

    def sync_to_scenario_run(self, run_status: Any) -> dict[str, Any]:
        """Resolve the current step from a ScenarioRunStatus-like object
        and push the visual clock to that step's t_offset_seconds."""
        if run_status is None:
            return {"status": "skipped", "reason": "no run"}
        current_step = getattr(run_status, "current_step", None)
        total_steps = getattr(run_status, "total_steps", None)
        scenario_id = getattr(run_status, "scenario_id", None)
        if current_step is None or total_steps is None:
            return {"status": "skipped", "reason": "run lacks step info"}
        t_offset = self._lookup_t_offset(scenario_id, current_step)
        with self._lock:
            self._scenario_run_id = getattr(run_status, "run_id", None) or self._scenario_run_id
        return self.sync_to_offset(t_offset)

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def capture_all_snapshots(self) -> dict[str, Any]:
        with self._lock:
            ctrl = self._controller_factory()
            result = ctrl.capture_all_snapshots()
            for captured in result.get("captured", []):
                if captured.get("status") == "ok":
                    self._record_camera_status(captured.get("camera_id"), captured)
            return result

    def capture_camera(self, camera_id: str) -> dict[str, Any]:
        with self._lock:
            ctrl = self._controller_factory()
            result = ctrl.capture_camera_snapshot(camera_id)
            if result.get("status") == "ok":
                self._record_camera_status(camera_id, result)
            return result

    def snapshot_path_for(self, camera_id: str) -> Path:
        return self._snapshot_dir / f"{camera_id}.png"

    # ------------------------------------------------------------------
    # Status accessors
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            ctrl = self._controller_factory()
            ctrl_status = ctrl.get_status()
            return {
                "active": self._active,
                "scenario_run_id": self._scenario_run_id,
                "last_t_offset_seconds": self._last_t_offset,
                "last_sync_at": self._last_sync_at,
                "last_step": self._last_step_payload,
                "last_error": self._last_error,
                "auto_capture_snapshots": self._auto_snapshots,
                "snapshot_dir": str(self._snapshot_dir),
                "controller": ctrl_status,
                "real_actor_mode": ctrl_status.get("real_actor_mode"),
                "connected": ctrl_status.get("connected", False),
            }

    def list_camera_status(self) -> list[dict[str, Any]]:
        """Return per-camera visual sync status. Pulls camera metadata from
        the controller's loaded config and overlays snapshot info."""
        ctrl = self._controller_factory()
        config = getattr(ctrl, "_config", {}) or {}
        cameras_out: list[dict[str, Any]] = []
        for cam in config.get("camera_markers", []):
            cam_id = cam["camera_id"]
            status_entry = dict(self._camera_status.get(cam_id, {}))
            snapshot_path = self.snapshot_path_for(cam_id)
            cameras_out.append(
                {
                    "camera_id": cam_id,
                    "zone_id": cam.get("zone_id"),
                    "pose": cam.get("pose"),
                    "snapshot_path": str(snapshot_path) if snapshot_path.exists() else None,
                    "snapshot_url": (
                        f"/api/visual-scenario/snapshots/{cam_id}"
                        if snapshot_path.exists()
                        else None
                    ),
                    "last_capture_at": status_entry.get("captured_at"),
                    "last_capture_bytes": status_entry.get("bytes"),
                    "last_status": status_entry.get("status") or "pending",
                }
            )
        return cameras_out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_camera_status(self, camera_id: str | None, payload: dict[str, Any]) -> None:
        if not camera_id:
            return
        snapshot = self._camera_status.setdefault(camera_id, {})
        snapshot.update(
            {
                "status": payload.get("status"),
                "captured_at": payload.get("captured_at"),
                "bytes": payload.get("bytes"),
                "snapshot_path": payload.get("snapshot_path"),
            }
        )

    def _lookup_t_offset(self, scenario_id: str | None, current_step: int) -> float:
        if scenario_id is None:
            return 0.0
        try:
            from app.services.scenario_engine_service import SCENARIO_CATALOGUE
        except Exception:  # pragma: no cover - scenario service optional
            return 0.0
        scenario = SCENARIO_CATALOGUE.get(scenario_id)
        if scenario is None or not scenario.timeline:
            return 0.0
        idx = max(0, min(current_step - 1, len(scenario.timeline) - 1))
        return float(scenario.timeline[idx].t_offset_seconds)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: VisualScenarioSyncService | None = None
_service_lock = threading.Lock()


def get_visual_scenario_sync_service() -> VisualScenarioSyncService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = VisualScenarioSyncService()
    return _service


def reset_visual_scenario_sync_service() -> None:
    """Test-only helper to drop the cached singleton."""
    global _service
    with _service_lock:
        _service = None
