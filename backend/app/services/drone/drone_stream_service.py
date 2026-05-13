from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from app.models.drone_simulation_models import DroneCameraFrame
from app.services.drone.drone_camera_registry import build_drone_source_id
from app.services.drone.drone_frame_adapter import DroneFrameAdapter
from app.services.drone.drone_simulation_service import DroneSimulationService
from core.event_bus import EventType, get_event_bus
from inference.model_pool import get_model_pool
from inference.stream.stream_processor import StreamProcessor
from ml.runtime import ModelRouter, system_boot_check


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DroneStreamService:
    """Multi-camera drone stream adapter that routes frames through StreamProcessor."""

    def __init__(
        self,
        simulation_service: DroneSimulationService,
        *,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._service = simulation_service
        self._cfg = dict(config or self._service.config.get("drone_stream") or {})
        self._enabled = bool(self._cfg.get("enabled", True))
        self._default_fps = float(self._cfg.get("default_fps", 5))
        self._max_fps = float(self._cfg.get("max_fps", 10))
        self._configured_cameras = [str(name).strip().lower() for name in (self._cfg.get("cameras") or ["front_center", "downward"]) if str(name).strip()]
        self._preview_all_cameras = bool(self._cfg.get("preview_all_cameras", True))
        self._process_all_cameras = bool(self._cfg.get("process_all_cameras", False))
        self._inference_cameras = {
            str(name).strip().lower()
            for name in (self._cfg.get("inference_cameras") or ["front_center"])
            if str(name).strip()
        }
        self._lock = threading.RLock()
        self._processors: dict[str, StreamProcessor] = {}
        self._latest_frames: dict[str, DroneCameraFrame] = {}
        self._running = False
        self._stats = {
            "frames_captured_total": 0,
            "frames_processed_total": 0,
            "frames_dropped_total": 0,
            "events_generated_total": 0,
            "anomalies_generated_total": 0,
            "last_error": None,
            "last_frame_at": None,
            "last_processed_at": None,
            "backpressure_drop_policy": "drop_when_slow",
        }

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        with self._lock:
            self._running = True

    def stop(self) -> None:
        with self._lock:
            self._running = False
            for processor in self._processors.values():
                try:
                    processor.stop()
                except Exception:
                    continue
            self._processors.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._stats)

    def latest_frames(self) -> dict[str, DroneCameraFrame]:
        with self._lock:
            return dict(self._latest_frames)

    def get_latest_frame(self, camera_name: str) -> DroneCameraFrame | None:
        source_id = build_drone_source_id(self._service.drone_id, camera_name)
        with self._lock:
            return self._latest_frames.get(source_id)

    def capture_and_process(
        self,
        *,
        mission_id: str | None = None,
        session_id: str | None = None,
    ) -> list[DroneCameraFrame]:
        if not self._enabled or not self._running:
            return []
        camera_names = self._capture_camera_names()
        started = time.perf_counter()
        frames = self._service.get_multi_camera_frames(camera_names)
        runtime_name = self._service.get_runtime_status().selected_runtime
        process_budget_seconds = 1.0 / max(1.0, min(self._max_fps, self._default_fps))
        for frame in frames:
            source_id = frame.source_id or build_drone_source_id(frame.drone_id, frame.camera_name)
            with self._lock:
                self._latest_frames[source_id] = frame
                self._stats["frames_captured_total"] += 1
                self._stats["last_frame_at"] = frame.timestamp
            if not frame.frame_available:
                continue
            if not self._should_process_camera(frame.camera_name):
                continue

            elapsed = time.perf_counter() - started
            if elapsed > process_budget_seconds:
                with self._lock:
                    self._stats["frames_dropped_total"] += 1
                continue

            try:
                decoded = DroneFrameAdapter.to_decoded_packet(
                    frame,
                    frame.telemetry,
                    mission_id=mission_id,
                    session_id=session_id,
                    city_runtime=runtime_name,
                )
                processor = self._ensure_processor(source_id, frame.camera_name)
                result = processor.process_decoded_packet(decoded)
                with self._lock:
                    self._stats["frames_processed_total"] += 1
                    self._stats["last_processed_at"] = _now_iso()
                self._publish_stream_event(frame, result, mission_id=mission_id, session_id=session_id, runtime_name=runtime_name)
                self._persist_observation(frame, mission_id=mission_id, session_id=session_id, runtime_name=runtime_name, result=result)
            except Exception as exc:
                with self._lock:
                    self._stats["last_error"] = str(exc)
                    self._stats["frames_dropped_total"] += 1
        return frames

    def _capture_camera_names(self) -> list[str]:
        if self._preview_all_cameras:
            return list(self._service.allowed_cameras)
        if self._configured_cameras:
            return list(self._configured_cameras)
        return [self._service.config.get("connection", {}).get("camera_name", "front_center")]

    def _should_process_camera(self, camera_name: str) -> bool:
        camera = str(camera_name).strip().lower()
        if self._process_all_cameras:
            return True
        return camera in self._inference_cameras

    def _ensure_processor(self, source_id: str, camera_name: str) -> StreamProcessor:
        processor = self._processors.get(source_id)
        if processor is not None:
            return processor
        pool = get_model_pool()
        if not pool.is_loaded:
            system_boot_check()
            router = ModelRouter()
            weapon = router.get_model("weapon")
            phone = router.get_model("phone")
            pool.load(weapon_path=weapon["resolved_path"], phone_path=phone["resolved_path"])
        processor = StreamProcessor(
            stream_id=f"cam_{source_id}",
            source=f"cosys_airsim://{self._service.drone_id}/{camera_name}",
            model_pool=pool,
        )
        processor.source_type = "drone_simulation"
        self._processors[source_id] = processor
        return processor

    def _publish_stream_event(
        self,
        frame: DroneCameraFrame,
        result: dict[str, Any] | None,
        *,
        mission_id: str | None,
        session_id: str | None,
        runtime_name: str | None,
    ) -> None:
        result = result or {}
        events_count = len(result.get("events") or [])
        anomalies_count = len(result.get("anomalies") or [])
        with self._lock:
            self._stats["events_generated_total"] += events_count
            self._stats["anomalies_generated_total"] += anomalies_count
        payload = {
            "event_type": "drone_stream_frame",
            "timestamp": _now_iso(),
            "drone_id": frame.drone_id,
            "camera_name": frame.camera_name,
            "source_id": frame.source_id or build_drone_source_id(frame.drone_id, frame.camera_name),
            "simulated": True,
            "operator_review_required": True,
            "mission_id": mission_id,
            "session_id": session_id,
            "city_runtime": runtime_name,
            "processing": {
                "events": events_count,
                "anomalies": anomalies_count,
                "incidents": len(result.get("incidents") or []),
                "scenarios": len(result.get("scenarios") or []),
            },
            "telemetry": frame.telemetry.model_dump(mode="json") if frame.telemetry is not None else None,
        }
        try:
            get_event_bus().publish(EventType.SYSTEM_EVENT, payload, source=frame.drone_id, priority=5)
        except Exception:
            pass

    def _persist_observation(
        self,
        frame: DroneCameraFrame,
        *,
        mission_id: str | None,
        session_id: str | None,
        runtime_name: str | None,
        result: dict[str, Any] | None,
    ) -> None:
        telemetry = frame.telemetry
        if telemetry is None:
            return
        event = self._service.create_observation_event(
            observation_type="frame",
            telemetry=telemetry,
            frame=frame,
            confidence=0.55,
        )
        event.metadata.update(
            {
                "drone_camera": frame.camera_name,
                "source_id": frame.source_id or build_drone_source_id(frame.drone_id, frame.camera_name),
                "city_runtime": runtime_name,
                "mission_id": mission_id,
                "session_id": session_id,
                "processing_result": {
                    "events": len((result or {}).get("events") or []),
                    "anomalies": len((result or {}).get("anomalies") or []),
                    "incidents": len((result or {}).get("incidents") or []),
                    "scenarios": len((result or {}).get("scenarios") or []),
                },
            }
        )
        self._service.persist_observation_event(event, telemetry=telemetry, frame_index=frame.frame_index)
