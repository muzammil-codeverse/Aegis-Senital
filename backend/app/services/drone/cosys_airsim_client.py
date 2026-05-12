from __future__ import annotations

import base64
import inspect
import logging
import math
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.models.drone_simulation_models import (
    DroneCameraFrame,
    DroneCommandResponse,
    DroneConnectionStatus,
    DroneHealthStatus,
    DroneOrientation,
    DronePose,
    DroneTelemetry,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meters_to_geo(latitude: float, longitude: float, north_m: float, east_m: float) -> tuple[float, float]:
    lat = float(latitude) + (float(north_m) / 111_320.0)
    cos_lat = math.cos(math.radians(max(min(lat, 89.9999), -89.9999)))
    lon = float(longitude)
    if abs(cos_lat) > 1e-6:
        lon += float(east_m) / (111_320.0 * cos_lat)
    return lat, lon


class CosysAirSimClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        vehicle_name: str,
        camera_name: str,
        timeout_seconds: float = 5.0,
        drone_id: str = "drone_sim_01",
        default_home: dict[str, Any] | None = None,
        image_type: str = "scene",
    ) -> None:
        self.host = host
        self.port = int(port)
        self.vehicle_name = vehicle_name
        self.camera_name = camera_name
        self.timeout_seconds = float(timeout_seconds)
        self.drone_id = drone_id
        self.default_home = dict(default_home or {})
        self.image_type = str(image_type or "scene").strip().lower()

        self._client_module: Any | None = None
        self._client: Any | None = None
        self._connected = False
        self._frame_index = 0
        self._last_error: str | None = None
        self._latest_telemetry: DroneTelemetry | None = None
        self._latest_frame: DroneCameraFrame | None = None

    def connect(self) -> DroneConnectionStatus:
        endpoint = f"{self.host}:{self.port}"
        module = self._load_client_module()
        if module is None:
            self._connected = False
            return DroneConnectionStatus(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                status="disconnected",
                connected=False,
                endpoint=endpoint,
                vehicle_name=self.vehicle_name,
                camera_name=self.camera_name,
                last_error=self._last_error,
            )

        if not self._port_open():
            self._connected = False
            self._client = None
            self._last_error = (
                f"Cosys-AirSim runtime is not reachable at {endpoint}. "
                "Start the simulated drone runtime to enable aerial observation."
            )
            return DroneConnectionStatus(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                status="disconnected",
                connected=False,
                endpoint=endpoint,
                vehicle_name=self.vehicle_name,
                camera_name=self.camera_name,
                last_error=self._last_error,
            )

        try:
            client = module.MultirotorClient(ip=self.host, port=self.port, timeout_value=self.timeout_seconds)
        except TypeError:
            client = module.MultirotorClient(ip=self.host, port=self.port)
        except Exception as exc:
            self._client = None
            self._connected = False
            self._last_error = f"Failed to create Cosys-AirSim client: {exc}"
            return DroneConnectionStatus(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                status="disconnected",
                connected=False,
                endpoint=endpoint,
                vehicle_name=self.vehicle_name,
                camera_name=self.camera_name,
                last_error=self._last_error,
            )

        try:
            self._call(client.confirmConnection)
            self._client = client
            self._connected = True
            self._last_error = None
            return DroneConnectionStatus(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                status="connected",
                connected=True,
                endpoint=endpoint,
                vehicle_name=self.vehicle_name,
                camera_name=self.camera_name,
            )
        except Exception as exc:
            self._client = None
            self._connected = False
            self._last_error = (
                f"Cosys-AirSim RPC connection failed at {endpoint}: {exc}. "
                "The simulated drone is unavailable until the runtime is started."
            )
            return DroneConnectionStatus(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                status="disconnected",
                connected=False,
                endpoint=endpoint,
                vehicle_name=self.vehicle_name,
                camera_name=self.camera_name,
                last_error=self._last_error,
            )

    def disconnect(self) -> None:
        self._client = None
        self._connected = False

    def is_connected(self) -> bool:
        return bool(self._connected and self._client is not None)

    def get_telemetry(self) -> DroneTelemetry:
        if not self.is_connected():
            status = self.connect()
            if not status.connected:
                return DroneTelemetry(
                    drone_id=self.drone_id,
                    provider="cosys_airsim",
                    simulated=True,
                    camera_name=self.camera_name,
                    status="disconnected",
                    last_error=status.last_error,
                )

        try:
            state = self._call(self._client.getMultirotorState, vehicle_name=self.vehicle_name)
            kinematics = getattr(state, "kinematics_estimated", None)
            position = getattr(kinematics, "position", None)
            velocity = getattr(kinematics, "linear_velocity", None)
            orientation = getattr(kinematics, "orientation", None)
            pos = DronePose(
                x=float(getattr(position, "x_val", 0.0) or 0.0),
                y=float(getattr(position, "y_val", 0.0) or 0.0),
                z=float(getattr(position, "z_val", 0.0) or 0.0),
            )
            vel = DronePose(
                x=float(getattr(velocity, "x_val", 0.0) or 0.0),
                y=float(getattr(velocity, "y_val", 0.0) or 0.0),
                z=float(getattr(velocity, "z_val", 0.0) or 0.0),
            )
            attitude = self._orientation_from_quaternion(orientation)

            gps = getattr(state, "gps_location", None)
            latitude = getattr(gps, "latitude", None)
            longitude = getattr(gps, "longitude", None)
            altitude = getattr(gps, "altitude", None)

            if latitude is None or longitude is None:
                home_lat = self.default_home.get("latitude")
                home_lon = self.default_home.get("longitude")
                if home_lat is not None and home_lon is not None:
                    latitude, longitude = _meters_to_geo(float(home_lat), float(home_lon), pos.x, pos.y)
            if altitude is None:
                home_alt = self.default_home.get("altitude_meters")
                if home_alt is not None:
                    altitude = float(home_alt) + abs(pos.z)

            telemetry = DroneTelemetry(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                simulated=True,
                timestamp=_now_iso(),
                latitude=float(latitude) if latitude is not None else None,
                longitude=float(longitude) if longitude is not None else None,
                altitude_meters=float(altitude) if altitude is not None else None,
                position=pos,
                velocity=vel,
                orientation=attitude,
                camera_name=self.camera_name,
                status="connected",
                metadata={"vehicle_name": self.vehicle_name},
            )
            self._latest_telemetry = telemetry
            self._last_error = None
            return telemetry
        except Exception as exc:
            self._last_error = f"Failed to read simulated telemetry: {exc}"
            self._connected = False
            return DroneTelemetry(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                simulated=True,
                timestamp=_now_iso(),
                camera_name=self.camera_name,
                status="degraded",
                last_error=self._last_error,
            )

    def get_frame(self) -> DroneCameraFrame:
        telemetry = self._latest_telemetry or self.get_telemetry()
        if telemetry.status == "disconnected":
            return DroneCameraFrame(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                simulated=True,
                camera_name=self.camera_name,
                status="disconnected",
                frame_available=False,
                telemetry=telemetry,
                last_error=telemetry.last_error,
            )

        try:
            image_request = self._client_module.ImageRequest(
                self.camera_name,
                self._resolve_image_type(),
                False,
                False,
            )
            responses = self._call(self._client.simGetImages, [image_request], vehicle_name=self.vehicle_name)
            if not responses:
                raise RuntimeError("simGetImages returned no responses")
            response = responses[0]
            width = int(getattr(response, "width", 0) or 0)
            height = int(getattr(response, "height", 0) or 0)
            if width <= 0 or height <= 0:
                raise RuntimeError("simGetImages returned an empty frame")
            raw = np.frombuffer(getattr(response, "image_data_uint8", b""), dtype=np.uint8)
            if raw.size == 0:
                raise RuntimeError("simGetImages returned no frame bytes")
            frame = raw.reshape(height, width, 3)
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise RuntimeError("OpenCV failed to encode the simulated frame")
            self._frame_index += 1
            payload = base64.b64encode(encoded.tobytes()).decode("ascii")
            item = DroneCameraFrame(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                simulated=True,
                timestamp=_now_iso(),
                frame_index=self._frame_index,
                camera_name=self.camera_name,
                width=width,
                height=height,
                image_base64=payload,
                status="connected",
                frame_available=True,
                telemetry=telemetry,
                metadata={
                    "vehicle_name": self.vehicle_name,
                    "source_type": "drone_simulation",
                    "simulated": True,
                },
            )
            self._latest_frame = item
            self._last_error = None
            return item
        except Exception as exc:
            self._last_error = f"Failed to capture simulated frame: {exc}"
            self._connected = False
            return DroneCameraFrame(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                simulated=True,
                timestamp=_now_iso(),
                frame_index=self._frame_index,
                camera_name=self.camera_name,
                status="degraded",
                frame_available=False,
                telemetry=telemetry,
                last_error=self._last_error,
            )

    def takeoff(self) -> DroneCommandResponse:
        return self._run_command("takeoff", "takeoffAsync")

    def land(self) -> DroneCommandResponse:
        return self._run_command("land", "landAsync")

    def move_to_position(self, x: float, y: float, z: float, velocity: float) -> DroneCommandResponse:
        return self._run_command(
            "move_to_position",
            "moveToPositionAsync",
            float(x),
            float(y),
            float(z),
            float(velocity),
        )

    def hover(self) -> DroneCommandResponse:
        return self._run_command("hover", "hoverAsync")

    def get_health(self) -> DroneHealthStatus:
        telemetry = self._latest_telemetry
        frame = self._latest_frame
        connected = self.is_connected()
        status = "healthy" if connected and telemetry and frame and frame.frame_available else (
            "degraded" if connected else "disconnected"
        )
        return DroneHealthStatus(
            enabled=True,
            provider="cosys_airsim",
            status=status,
            simulator_connected=connected,
            telemetry_available=bool(telemetry and telemetry.status == "connected"),
            frame_available=bool(frame and frame.frame_available),
            active_session=False,
            last_error=self._last_error,
        )

    def _run_command(self, command: str, method_name: str, *args: Any) -> DroneCommandResponse:
        issued_at = _now_iso()
        if not self.is_connected():
            status = self.connect()
            if not status.connected:
                return DroneCommandResponse(
                    drone_id=self.drone_id,
                    provider="cosys_airsim",
                    simulated=True,
                    command=command,  # type: ignore[arg-type]
                    success=False,
                    status="denied",
                    detail=status.last_error or "Simulated drone runtime is disconnected.",
                    issued_at=issued_at,
                    completed_at=_now_iso(),
                )

        try:
            method = getattr(self._client, method_name)
            result = self._call(method, *args, vehicle_name=self.vehicle_name)
            if hasattr(result, "join"):
                result.join()
            self._last_error = None
            return DroneCommandResponse(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                simulated=True,
                command=command,  # type: ignore[arg-type]
                success=True,
                status="ok",
                detail="Simulated drone command accepted.",
                issued_at=issued_at,
                completed_at=_now_iso(),
            )
        except Exception as exc:
            self._last_error = f"Simulated drone command failed: {exc}"
            self._connected = False
            return DroneCommandResponse(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                simulated=True,
                command=command,  # type: ignore[arg-type]
                success=False,
                status="failed",
                detail=self._last_error,
                issued_at=issued_at,
                completed_at=_now_iso(),
            )

    def _load_client_module(self) -> Any | None:
        if self._client_module is not None:
            return self._client_module
        try:
            import cosysairsim as module

            self._client_module = module
            return module
        except Exception:
            pass
        try:
            import airsim as module

            self._client_module = module
            return module
        except Exception:
            pass

        pyclient_dir = os.environ.get(
            "AEGIS_COSYS_AIRSIM_PYTHONCLIENT_DIR",
            r"C:\AegisExternalTools\drone_sim\cosys_airsim\Cosys-AirSim\PythonClient",
        )
        if pyclient_dir and Path(pyclient_dir).exists() and pyclient_dir not in sys.path:
            sys.path.insert(0, pyclient_dir)
        for module_name in ("cosysairsim", "airsim"):
            try:
                module = __import__(module_name)
                self._client_module = module
                return module
            except Exception:
                continue
        self._last_error = (
            "cosysairsim is not installed. Install the prepared Python client or "
            "set AEGIS_COSYS_AIRSIM_PYTHONCLIENT_DIR before enabling drone simulation."
        )
        return None

    def _resolve_image_type(self) -> Any:
        module = self._client_module
        image_type = getattr(module, "ImageType", None)
        if image_type is None:
            return 0
        mapping = {
            "scene": getattr(image_type, "Scene", 0),
            "segmentation": getattr(image_type, "Segmentation", 5),
            "depth": getattr(image_type, "DepthPlanar", 1),
        }
        return mapping.get(self.image_type, getattr(image_type, "Scene", 0))

    def _port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(max(0.5, self.timeout_seconds))
            try:
                return sock.connect_ex((self.host, self.port)) == 0
            except OSError:
                return False

    @staticmethod
    def _call(method: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            signature = inspect.signature(method)
        except (TypeError, ValueError):
            signature = None
        if signature is not None:
            accepted = {
                key: value
                for key, value in kwargs.items()
                if key in signature.parameters
            }
        else:
            accepted = kwargs
        return method(*args, **accepted)

    def _orientation_from_quaternion(self, orientation: Any) -> DroneOrientation:
        if orientation is None:
            return DroneOrientation()
        module = self._client_module
        try:
            if hasattr(module, "to_eularian_angles"):
                pitch, roll, yaw = module.to_eularian_angles(orientation)
                return DroneOrientation(pitch=float(pitch), roll=float(roll), yaw=float(yaw))
        except Exception:
            pass
        x = float(getattr(orientation, "x_val", 0.0) or 0.0)
        y = float(getattr(orientation, "y_val", 0.0) or 0.0)
        z = float(getattr(orientation, "z_val", 0.0) or 0.0)
        w = float(getattr(orientation, "w_val", 1.0) or 1.0)
        sinr_cosp = 2.0 * (w * x + y * z)
        cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        sinp = 2.0 * (w * y - z * x)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2.0, sinp)
        else:
            pitch = math.asin(sinp)
        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        return DroneOrientation(pitch=float(pitch), roll=float(roll), yaw=float(yaw))
