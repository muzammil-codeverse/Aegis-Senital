from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.camera_models import CameraSourceType, CameraStatus
from app.models.drone_simulation_models import (
    DroneCameraFrame,
    DroneCommandResponse,
    DroneConnectionStatus,
    DroneFlightPathPoint,
    DroneHealthStatus,
    DroneObservationEvent,
    DroneTelemetry,
)
from app.models.gis_models import CameraGeoProfile
from app.models.incident_models import IncidentEventRecord
from app.repositories.gis_repository import get_gis_repository
from app.repositories.incident_repository import get_incident_repository
from app.security.config import PROJECT_ROOT
from app.services.camera_registry import get_camera_registry
from app.services.drone.cosys_airsim_client import CosysAirSimClient
from inference.config_runtime import load_runtime_config
from inference.metrics import metrics
from inference.monitoring.metrics import get_metrics

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metric_increment(name: str, value: int = 1) -> None:
    try:
        metrics.increment(name, value)
    except Exception:
        pass
    try:
        get_metrics().increment(name, value)
    except Exception:
        pass


def _metric_set(name: str, value: int | float) -> None:
    try:
        metrics.set_value(name, value)
    except Exception:
        pass
    try:
        get_metrics().record_segmentation_value(name, value)
    except Exception:
        pass


class DroneSimulationService:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        raw = config or load_runtime_config("drone_simulation")
        self._raw_config = raw
        self._config = dict(raw.get("drone_simulation") or {})
        connection = dict(self._config.get("connection") or {})
        stream = dict(self._config.get("stream") or {})
        capture = dict(self._config.get("capture") or {})
        gis = dict(self._config.get("gis") or {})
        self._stream_camera_id = str(stream.get("pseudo_camera_id") or "drone_sim_01")
        self._feed_name = str(stream.get("feed_name") or "Simulated Drone Feed")
        self._default_home = dict(gis.get("default_home") or {})
        self._client = CosysAirSimClient(
            host=str(connection.get("host") or "127.0.0.1"),
            port=int(connection.get("port") or 41451),
            vehicle_name=str(connection.get("vehicle_name") or "Drone1"),
            camera_name=str(connection.get("camera_name") or "front_center"),
            timeout_seconds=float(connection.get("timeout_seconds") or 5.0),
            drone_id=self._stream_camera_id,
            default_home=self._default_home,
            image_type=str(capture.get("image_type") or "scene"),
        )
        self._last_status: DroneConnectionStatus | None = None
        self._last_frame: DroneCameraFrame | None = None
        self._last_telemetry: DroneTelemetry | None = None
        self._last_health: DroneHealthStatus | None = None
        self.ensure_registered()

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    @property
    def drone_id(self) -> str:
        return self._stream_camera_id

    def ensure_registered(self) -> None:
        registry = get_camera_registry()
        camera = registry.get_camera(self._stream_camera_id)
        source_uri = (
            f"cosys_airsim://{self._client.host}:{self._client.port}/"
            f"{self._client.vehicle_name}/{self._client.camera_name}"
        )
        metadata = {
            "source_type": "drone_simulation",
            "simulated": True,
            "provider": "cosys_airsim",
            "vehicle_name": self._client.vehicle_name,
            "camera_name": self._client.camera_name,
            "safety_badge": "Simulated drone feed",
        }
        if camera is None:
            try:
                registry.register_camera(
                    {
                        "camera_id": self._stream_camera_id,
                        "name": self._feed_name,
                        "source_type": CameraSourceType.DRONE_SIM.value,
                        "source_uri": source_uri,
                        "status": CameraStatus.OFFLINE.value,
                        "enabled": True,
                        "fov_degrees": 70,
                        "coverage_radius": 150,
                        "location": {"region": "simulated_airspace"},
                        "zone": "simulated_airspace",
                        "metadata": metadata,
                    }
                )
            except ValueError:
                pass
        else:
            registry.update_camera(
                self._stream_camera_id,
                {
                    "name": self._feed_name,
                    "source_uri": source_uri,
                    "enabled": True,
                    "metadata": {**dict(camera.metadata or {}), **metadata},
                },
            )

    def connect(self) -> DroneConnectionStatus:
        _metric_increment("drone_sim_connection_attempts_total")
        self.ensure_registered()
        status = self._client.connect()
        self._last_status = status
        if not status.connected:
            _metric_increment("drone_sim_connection_failures_total")
            get_camera_registry().set_camera_status(self._stream_camera_id, CameraStatus.OFFLINE.value, status.last_error)
        else:
            get_camera_registry().set_camera_status(self._stream_camera_id, CameraStatus.ONLINE.value)
        return status

    def disconnect(self) -> None:
        self._client.disconnect()
        get_camera_registry().set_camera_status(self._stream_camera_id, CameraStatus.OFFLINE.value, "operator stop")

    def is_connected(self) -> bool:
        return self._client.is_connected()

    def get_telemetry(self) -> DroneTelemetry:
        telemetry = self._client.get_telemetry()
        self._last_telemetry = telemetry
        if telemetry.status == "connected":
            _metric_increment("drone_sim_telemetry_updates_total")
            self._update_registered_geo_profile(telemetry)
            get_camera_registry().mark_frame_seen(self._stream_camera_id, timestamp=time.time())
        return telemetry

    def get_frame(self) -> DroneCameraFrame:
        started = time.perf_counter()
        frame = self._client.get_frame()
        self._last_frame = frame
        if frame.frame_available:
            _metric_increment("drone_sim_frames_captured_total")
        _metric_set("drone_sim_frame_latency_ms", round((time.perf_counter() - started) * 1000.0, 2))
        return frame

    def takeoff(self) -> DroneCommandResponse:
        response = self._client.takeoff()
        self._record_command_metrics(response)
        return response

    def land(self) -> DroneCommandResponse:
        response = self._client.land()
        self._record_command_metrics(response)
        return response

    def move_to_position(self, x: float, y: float, z: float, velocity: float) -> DroneCommandResponse:
        response = self._client.move_to_position(x, y, z, velocity)
        self._record_command_metrics(response)
        return response

    def hover(self) -> DroneCommandResponse:
        response = self._client.hover()
        self._record_command_metrics(response)
        return response

    def get_health(self, *, active_session: bool = False) -> DroneHealthStatus:
        health = self._client.get_health()
        health.active_session = active_session
        self._last_health = health
        return health

    def latest_frame(self) -> DroneCameraFrame | None:
        return self._last_frame

    def latest_telemetry(self) -> DroneTelemetry | None:
        return self._last_telemetry

    def build_flight_path_point(self, telemetry: DroneTelemetry) -> DroneFlightPathPoint | None:
        if telemetry.latitude is None or telemetry.longitude is None:
            return None
        return DroneFlightPathPoint(
            drone_id=self._stream_camera_id,
            camera_id=self._stream_camera_id,
            source_type="drone_simulation",
            simulated=True,
            timestamp=telemetry.timestamp,
            latitude=float(telemetry.latitude),
            longitude=float(telemetry.longitude),
            altitude_meters=telemetry.altitude_meters,
            position=telemetry.position,
            orientation=telemetry.orientation,
            metadata={"provider": telemetry.provider, "camera_name": telemetry.camera_name},
        )

    def create_observation_event(
        self,
        *,
        observation_type: str,
        telemetry: DroneTelemetry | None,
        frame: DroneCameraFrame | None = None,
        confidence: float = 0.5,
        evidence_refs: list[str] | None = None,
    ) -> DroneObservationEvent:
        return DroneObservationEvent(
            event_id=f"drn_{uuid.uuid4().hex[:16]}",
            observation_type=observation_type,  # type: ignore[arg-type]
            source_type="drone_simulation",
            source_id=self._stream_camera_id,
            drone_id=self._stream_camera_id,
            simulated=True,
            timestamp=(frame.timestamp if frame is not None else telemetry.timestamp if telemetry is not None else _now_iso()),
            latitude=telemetry.latitude if telemetry is not None else None,
            longitude=telemetry.longitude if telemetry is not None else None,
            altitude_meters=telemetry.altitude_meters if telemetry is not None else None,
            confidence=confidence,
            safe_label="Simulated aerial observation",
            evidence_refs=list(evidence_refs or []),
            metadata={
                "camera_name": self._client.camera_name,
                "frame_index": getattr(frame, "frame_index", None),
                "provider": "cosys_airsim",
                "simulated": True,
            },
        )

    def persist_observation_event(
        self,
        event: DroneObservationEvent,
        *,
        telemetry: DroneTelemetry | None = None,
        frame_index: int | None = None,
    ) -> IncidentEventRecord:
        metadata = dict(event.metadata or {})
        metadata.update(
            {
                "safe_label": event.safe_label,
                "simulated": True,
                "source_type": "drone_simulation",
                "latitude": event.latitude,
                "longitude": event.longitude,
                "altitude_meters": event.altitude_meters,
                "telemetry": telemetry.model_dump(mode="json") if telemetry is not None else None,
            }
        )
        record = IncidentEventRecord(
            incident_id=event.event_id,
            event_id=event.event_id,
            source_type="drone_simulation",
            camera_id=self._stream_camera_id,
            session_id=self._stream_camera_id,
            event_type=f"drone_{event.observation_type}",
            severity="medium",
            risk_score=float(event.confidence),
            timestamp=event.timestamp,
            frame_index=frame_index,
            time_offset_seconds=None,
            track_ids=[],
            object_refs=[event.source_id],
            identity_ids=[],
            summary=event.safe_label,
            metadata=metadata,
        )
        return get_incident_repository().append_event(record)

    def _update_registered_geo_profile(self, telemetry: DroneTelemetry) -> None:
        if telemetry.latitude is None or telemetry.longitude is None:
            return
        profile = CameraGeoProfile(
            camera_id=self._stream_camera_id,
            name=self._feed_name,
            latitude=float(telemetry.latitude),
            longitude=float(telemetry.longitude),
            altitude_meters=telemetry.altitude_meters,
            heading_degrees=float(telemetry.orientation.yaw or 0.0),
            fov_degrees=70.0,
            coverage_radius_meters=150.0,
            region="simulated_airspace",
            metadata={
                "source_type": "drone_simulation",
                "simulated": True,
                "provider": telemetry.provider,
                "camera_name": telemetry.camera_name,
                "last_telemetry_at": telemetry.timestamp,
            },
        )
        get_gis_repository().upsert_camera_geo_profile(profile)
        get_camera_registry().update_camera(
            self._stream_camera_id,
            {
                "status": CameraStatus.ONLINE.value,
                "location": {
                    "latitude": profile.latitude,
                    "longitude": profile.longitude,
                    "altitude_meters": profile.altitude_meters,
                    "region": profile.region,
                },
                "view_direction_degrees": profile.heading_degrees,
                "fov_degrees": profile.fov_degrees,
                "coverage_radius": profile.coverage_radius_meters,
                "metadata": {
                    **dict((get_camera_registry().get_camera(self._stream_camera_id).metadata if get_camera_registry().get_camera(self._stream_camera_id) else {}) or {}),
                    "source_type": "drone_simulation",
                    "simulated": True,
                    "provider": telemetry.provider,
                    "last_telemetry_at": telemetry.timestamp,
                },
            },
        )

    def _record_command_metrics(self, response: DroneCommandResponse) -> None:
        _metric_increment("drone_sim_commands_total")
        if not response.success:
            _metric_increment("drone_sim_command_failures_total")


_service: DroneSimulationService | None = None


def get_drone_simulation_service() -> DroneSimulationService:
    global _service
    if _service is None:
        _service = DroneSimulationService()
    return _service
