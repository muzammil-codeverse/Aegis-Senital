from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from app.models.drone_simulation_models import (
    DroneCameraFrame,
    DroneCommandResponse,
    DroneFlightPathPoint,
    DroneSimulationSession,
    DroneTelemetry,
)
from app.models.security_models import UserAccount
from app.services.drone.drone_simulation_service import get_drone_simulation_service
from core.event_bus import EventType, get_event_bus
from inference.drone.drone_frame_adapter import DroneFrameAdapter
from inference.metrics import metrics
from inference.model_pool import get_model_pool
from inference.monitoring.metrics import get_metrics
from inference.stream.stream_processor import StreamProcessor
from ml.runtime import ModelRouter, system_boot_check


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metric_set(name: str, value: int | float) -> None:
    try:
        metrics.set_value(name, value)
    except Exception:
        pass
    try:
        get_metrics().record_segmentation_value(name, value)
    except Exception:
        pass


class DroneSimulationSessionManager:
    def __init__(self) -> None:
        self._service = get_drone_simulation_service()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._session: DroneSimulationSession = DroneSimulationSession(
            session_id=f"drn_session_{uuid.uuid4().hex[:12]}",
            drone_id=self._service.drone_id,
            provider="cosys_airsim",
            simulated=True,
            status="idle",
            active=False,
            stream_processor_enabled=bool(
                (self._service.config.get("stream") or {}).get("process_through_stream_processor", True)
            ),
        )
        self._latest_telemetry: DroneTelemetry | None = None
        self._latest_frame: DroneCameraFrame | None = None
        self._flight_path: list[DroneFlightPathPoint] = []
        self._processor: StreamProcessor | None = None
        self._last_telemetry_event_ts = 0.0
        self._last_frame_event_ts = 0.0

    def start_session(self, user: UserAccount) -> DroneSimulationSession:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._session
            self._stop_event.clear()
            self._session = DroneSimulationSession(
                session_id=f"drn_session_{uuid.uuid4().hex[:12]}",
                drone_id=self._service.drone_id,
                provider="cosys_airsim",
                simulated=True,
                status="starting",
                active=True,
                started_at=_now_iso(),
                updated_at=_now_iso(),
                operator_id=user.user_id,
                operator_name=user.username,
                stream_processor_enabled=bool(
                    (self._service.config.get("stream") or {}).get("process_through_stream_processor", True)
                ),
            )
            self._flight_path = []
            self._thread = threading.Thread(
                target=self._run_loop,
                name="drone-simulation-session",
                daemon=True,
            )
            self._thread.start()
            _metric_set("drone_sim_active_sessions", 1)
            return self._session

    def stop_session(self, user: UserAccount) -> DroneSimulationSession:
        del user
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        with self._lock:
            if self._processor is not None:
                try:
                    self._processor.stop()
                except Exception:
                    pass
            self._processor = None
            self._service.disconnect()
            self._session.active = False
            self._session.status = "stopped"
            self._session.stopped_at = _now_iso()
            self._session.updated_at = _now_iso()
        _metric_set("drone_sim_active_sessions", 0)
        return self._session

    def get_session_status(self) -> DroneSimulationSession:
        with self._lock:
            return self._session.model_copy(deep=True)

    def get_latest_telemetry(self) -> DroneTelemetry | None:
        return self._latest_telemetry

    def get_latest_frame(self) -> DroneCameraFrame | None:
        return self._latest_frame

    def get_flight_path(self) -> list[DroneFlightPathPoint]:
        return [item.model_copy(deep=True) for item in self._flight_path]

    def takeoff(self) -> DroneCommandResponse:
        return self._service.takeoff()

    def land(self) -> DroneCommandResponse:
        return self._service.land()

    def hover(self) -> DroneCommandResponse:
        return self._service.hover()

    def move_to_position(self, x: float, y: float, z: float, velocity: float) -> DroneCommandResponse:
        return self._service.move_to_position(x, y, z, velocity)

    def _ensure_processor(self) -> StreamProcessor | None:
        if self._processor is not None:
            return self._processor
        if not bool((self._service.config.get("stream") or {}).get("process_through_stream_processor", True)):
            return None
        pool = get_model_pool()
        if not pool.is_loaded:
            system_boot_check()
            router = ModelRouter()
            weapon = router.get_model("weapon")
            phone = router.get_model("phone")
            pool.load(weapon_path=weapon["resolved_path"], phone_path=phone["resolved_path"])
        self._processor = StreamProcessor(
            stream_id=f"cam_{self._service.drone_id}",
            source=f"cosys_airsim://{self._service.drone_id}",
            model_pool=pool,
        )
        self._processor.source_type = "drone_simulation"
        return self._processor

    def _run_loop(self) -> None:
        config = self._service.config
        telemetry_hz = max(1.0, float((config.get("telemetry") or {}).get("poll_hz", 5)))
        frame_fps = max(1.0, float((config.get("capture") or {}).get("target_fps", 10)))
        telemetry_interval = 1.0 / telemetry_hz
        frame_interval = 1.0 / frame_fps
        next_telemetry_at = 0.0
        next_frame_at = 0.0
        self._ensure_processor()
        with self._lock:
            self._session.status = "running"
            self._session.updated_at = _now_iso()
        self._publish_status_event("drone_simulation_started")
        while not self._stop_event.is_set():
            now = time.monotonic()
            if now >= next_telemetry_at:
                self._poll_telemetry()
                next_telemetry_at = now + telemetry_interval
            if now >= next_frame_at:
                self._poll_frame()
                next_frame_at = now + frame_interval
            time.sleep(0.02)
        with self._lock:
            self._session.active = False
            self._session.status = "stopped"
            self._session.stopped_at = _now_iso()
            self._session.updated_at = _now_iso()
        self._publish_status_event("drone_simulation_stopped")

    def _poll_telemetry(self) -> None:
        telemetry = self._service.get_telemetry()
        self._latest_telemetry = telemetry
        with self._lock:
            self._session.telemetry_updates_total += 1
            self._session.updated_at = _now_iso()
            if telemetry.last_error:
                self._session.last_error = telemetry.last_error
                if telemetry.status == "disconnected":
                    self._session.status = "degraded"
        path_point = self._service.build_flight_path_point(telemetry)
        if path_point is not None:
            self._flight_path.append(path_point)
            max_age = int((self._service.config.get("investigation") or {}).get("max_observation_age_seconds", 120))
            cutoff = time.time() - max_age
            self._flight_path = [
                item for item in self._flight_path
                if datetime.fromisoformat(item.timestamp.replace("Z", "+00:00")).timestamp() >= cutoff
            ][-500:]
        if telemetry.status == "connected" and (time.time() - self._last_telemetry_event_ts) >= 1.0:
            event = self._service.create_observation_event(observation_type="telemetry", telemetry=telemetry, confidence=0.68)
            self._service.persist_observation_event(event, telemetry=telemetry)
            self._last_telemetry_event_ts = time.time()
        self._publish_status_event("drone_telemetry")

    def _poll_frame(self) -> None:
        frame = self._service.get_frame()
        self._latest_frame = frame
        if not frame.frame_available:
            return
        decoded = DroneFrameAdapter.to_decoded_packet(frame, frame.telemetry)
        processor = self._ensure_processor()
        if processor is not None:
            result = processor.process_decoded_packet(decoded)
            _metric_set("drone_sim_frames_processed_total", self._session.frames_processed_total + 1)
            if isinstance(result, dict):
                frame.metadata["processing_result"] = {
                    "events": len(result.get("events") or []),
                    "anomalies": len(result.get("anomalies") or []),
                    "incidents": len(result.get("incidents") or []),
                    "scenarios": len(result.get("scenarios") or []),
                }
        with self._lock:
            self._session.frame_index = frame.frame_index
            self._session.frames_processed_total += 1
            self._session.updated_at = _now_iso()
        if (time.time() - self._last_frame_event_ts) >= 1.0:
            event = self._service.create_observation_event(
                observation_type="frame",
                telemetry=frame.telemetry,
                frame=frame,
                confidence=0.55,
            )
            self._service.persist_observation_event(event, telemetry=frame.telemetry, frame_index=frame.frame_index)
            self._last_frame_event_ts = time.time()
        self._publish_status_event("drone_frame")

    def _publish_status_event(self, event_type: str) -> None:
        payload: dict[str, Any] = {
            "event_type": event_type,
            "drone_id": self._service.drone_id,
            "simulated": True,
            "timestamp": _now_iso(),
            "session": self._session.model_dump(mode="json"),
        }
        if self._latest_telemetry is not None:
            payload["telemetry"] = self._latest_telemetry.model_dump(mode="json")
        try:
            get_event_bus().publish(EventType.SYSTEM_EVENT, payload, source=self._service.drone_id, priority=5)
        except Exception:
            pass


_manager: DroneSimulationSessionManager | None = None


def get_drone_simulation_session_manager() -> DroneSimulationSessionManager:
    global _manager
    if _manager is None:
        _manager = DroneSimulationSessionManager()
    return _manager
