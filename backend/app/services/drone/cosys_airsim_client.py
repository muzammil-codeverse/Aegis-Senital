from __future__ import annotations

import base64
import inspect
import json
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
    DroneRuntimeStatus,
    DroneTelemetry,
)
from app.services.drone.drone_camera_registry import SUPPORTED_DRONE_CAMERAS, build_drone_source_id

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
        host: str | None = None,
        port: int | None = None,
        vehicle_name: str | None = None,
        camera_name: str | None = None,
        timeout_seconds: float = 5.0,
        drone_id: str = "drone_sim_01",
        default_home: dict[str, Any] | None = None,
        image_type: str = "scene",
        allowed_cameras: list[str] | tuple[str, ...] | None = None,
        runtime_inventory_path: str | Path = "storage/drone_sim/runtime_inventory.json",
    ) -> None:
        self.host = str(host or os.environ.get("AEGIS_AIRSIM_HOST") or "127.0.0.1")
        self.port = int(port or os.environ.get("AEGIS_AIRSIM_PORT") or 41451)
        self.vehicle_name = str(vehicle_name or os.environ.get("AEGIS_AIRSIM_VEHICLE") or "Drone1")
        self.camera_name = str(camera_name or os.environ.get("AEGIS_AIRSIM_CAMERA") or "front_center")
        self.timeout_seconds = float(timeout_seconds)
        self.drone_id = drone_id
        self.default_home = dict(default_home or {})
        self.image_type = str(image_type or "scene").strip().lower()
        self.allowed_cameras = tuple(
            str(camera).strip().lower()
            for camera in (allowed_cameras or SUPPORTED_DRONE_CAMERAS)
            if str(camera).strip()
        )
        if self.camera_name not in self.allowed_cameras:
            self.allowed_cameras = tuple(dict.fromkeys((self.camera_name, *self.allowed_cameras)))
        self.runtime_inventory_path = Path(runtime_inventory_path)
        self.city_runtime = str(os.environ.get("AEGIS_DRONE_RUNTIME_NAME") or "").strip() or None

        self._client_module: Any | None = None
        self._client: Any | None = None
        self._connected = False
        self._frame_index = 0
        self._last_error: str | None = None
        self._latest_telemetry: DroneTelemetry | None = None
        self._latest_frame: DroneCameraFrame | None = None
        self._supports_named_vehicle_calls: bool | None = None

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
        self._supports_named_vehicle_calls = None

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
            state = self._call_with_vehicle_fallback(self._client.getMultirotorState)
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
                city_runtime=self._runtime_name_hint(),
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
                city_runtime=self._runtime_name_hint(),
                status="degraded",
                last_error=self._last_error,
            )

    def get_frame(self) -> DroneCameraFrame:
        return self.get_camera_frame(self.camera_name)

    def get_camera_frame(self, camera_name: str) -> DroneCameraFrame:
        camera = self._normalize_camera_name(camera_name)
        telemetry = self._latest_telemetry or self.get_telemetry()
        if telemetry.status == "disconnected":
            return DroneCameraFrame(
                drone_id=self.drone_id,
                provider="cosys_airsim",
                simulated=True,
                camera_name=camera,
                source_id=build_drone_source_id(self.drone_id, camera),
                city_runtime=self._runtime_name_hint(),
                status="disconnected",
                frame_available=False,
                telemetry=telemetry,
                last_error=telemetry.last_error,
            )

        frames = self.get_multi_camera_frames([camera], telemetry=telemetry)
        if frames:
            return frames[0]
        return DroneCameraFrame(
            drone_id=self.drone_id,
            provider="cosys_airsim",
            simulated=True,
            camera_name=camera,
            source_id=build_drone_source_id(self.drone_id, camera),
            city_runtime=self._runtime_name_hint(),
            status="degraded",
            frame_available=False,
            telemetry=telemetry,
            last_error=self._last_error or "No frame returned from runtime",
        )

    def get_multi_camera_frames(
        self,
        camera_names: list[str],
        *,
        telemetry: DroneTelemetry | None = None,
    ) -> list[DroneCameraFrame]:
        if not camera_names:
            return []
        safe_cameras = [self._normalize_camera_name(name) for name in camera_names]
        telemetry = telemetry or self._latest_telemetry or self.get_telemetry()
        if telemetry.status == "disconnected":
            return [
                DroneCameraFrame(
                    drone_id=self.drone_id,
                    provider="cosys_airsim",
                    simulated=True,
                    camera_name=name,
                    source_id=build_drone_source_id(self.drone_id, name),
                    city_runtime=self._runtime_name_hint(),
                    status="disconnected",
                    frame_available=False,
                    telemetry=telemetry,
                    last_error=telemetry.last_error,
                )
                for name in safe_cameras
            ]

        try:
            image_requests = [
                self._client_module.ImageRequest(
                    camera_name,
                    self._resolve_image_type(),
                    False,
                    False,
                )
                for camera_name in safe_cameras
            ]
            responses = self._call_with_vehicle_fallback(self._client.simGetImages, image_requests)
            if not responses:
                raise RuntimeError("simGetImages returned no responses")

            frames: list[DroneCameraFrame] = []
            runtime_name = self._runtime_name_hint()
            for index, camera_name in enumerate(safe_cameras):
                response = responses[index] if index < len(responses) else None
                if response is None:
                    frames.append(
                        DroneCameraFrame(
                            drone_id=self.drone_id,
                            provider="cosys_airsim",
                            simulated=True,
                            camera_name=camera_name,
                            source_id=build_drone_source_id(self.drone_id, camera_name),
                            city_runtime=runtime_name,
                            status="degraded",
                            frame_available=False,
                            telemetry=telemetry,
                            last_error=f"Camera '{camera_name}' returned no response",
                        )
                    )
                    continue
                width = int(getattr(response, "width", 0) or 0)
                height = int(getattr(response, "height", 0) or 0)
                if width <= 0 or height <= 0:
                    frames.append(
                        DroneCameraFrame(
                            drone_id=self.drone_id,
                            provider="cosys_airsim",
                            simulated=True,
                            camera_name=camera_name,
                            source_id=build_drone_source_id(self.drone_id, camera_name),
                            city_runtime=runtime_name,
                            status="degraded",
                            frame_available=False,
                            telemetry=telemetry,
                            last_error=f"Camera '{camera_name}' returned an empty frame",
                        )
                    )
                    continue
                raw = np.frombuffer(getattr(response, "image_data_uint8", b""), dtype=np.uint8)
                if raw.size == 0:
                    frames.append(
                        DroneCameraFrame(
                            drone_id=self.drone_id,
                            provider="cosys_airsim",
                            simulated=True,
                            camera_name=camera_name,
                            source_id=build_drone_source_id(self.drone_id, camera_name),
                            city_runtime=runtime_name,
                            status="degraded",
                            frame_available=False,
                            telemetry=telemetry,
                            last_error=f"Camera '{camera_name}' returned no frame bytes",
                        )
                    )
                    continue
                frame = raw.reshape(height, width, 3)
                ok, encoded = cv2.imencode(".jpg", frame)
                if not ok:
                    frames.append(
                        DroneCameraFrame(
                            drone_id=self.drone_id,
                            provider="cosys_airsim",
                            simulated=True,
                            camera_name=camera_name,
                            source_id=build_drone_source_id(self.drone_id, camera_name),
                            city_runtime=runtime_name,
                            status="degraded",
                            frame_available=False,
                            telemetry=telemetry,
                            last_error=f"Camera '{camera_name}' failed JPEG encoding",
                        )
                    )
                    continue

                self._frame_index += 1
                payload = base64.b64encode(encoded.tobytes()).decode("ascii")
                item = DroneCameraFrame(
                    drone_id=self.drone_id,
                    provider="cosys_airsim",
                    simulated=True,
                    timestamp=_now_iso(),
                    frame_index=self._frame_index,
                    camera_name=camera_name,
                    source_id=build_drone_source_id(self.drone_id, camera_name),
                    city_runtime=runtime_name,
                    width=width,
                    height=height,
                    image_base64=payload,
                    status="connected",
                    frame_available=True,
                    telemetry=telemetry,
                    metadata={
                        "vehicle_name": self.vehicle_name,
                        "source_type": "drone_simulation",
                        "source_id": build_drone_source_id(self.drone_id, camera_name),
                        "simulated": True,
                    },
                )
                frames.append(item)
                if camera_name == self.camera_name:
                    self._latest_frame = item
            self._last_error = None
            return frames
        except Exception as exc:
            self._last_error = f"Failed to capture simulated frame batch: {exc}"
            self._connected = False
            return [
                DroneCameraFrame(
                    drone_id=self.drone_id,
                    provider="cosys_airsim",
                    simulated=True,
                    timestamp=_now_iso(),
                    frame_index=self._frame_index,
                    camera_name=name,
                    source_id=build_drone_source_id(self.drone_id, name),
                    city_runtime=self._runtime_name_hint(),
                    status="degraded",
                    frame_available=False,
                    telemetry=telemetry,
                    last_error=self._last_error,
                )
                for name in safe_cameras
            ]

    def get_vehicle_state(self) -> DroneTelemetry:
        return self.get_telemetry()

    def get_city_runtime_status(self) -> DroneRuntimeStatus:
        available: list[str] = []
        selected = self.city_runtime
        if self.runtime_inventory_path.exists():
            try:
                payload = json.loads(self.runtime_inventory_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            selected = str(payload.get("selected_runtime") or selected or "").strip() or None
            available = [str(item) for item in (payload.get("available_runtimes") or []) if str(item).strip()]
        connected = self.is_connected()
        port_open = self._port_open()
        return DroneRuntimeStatus(
            selected_runtime=selected,
            available_runtimes=available,
            fallback_used=selected == "Blocks",
            endpoint=f"{self.host}:{self.port}",
            port_open=port_open,
            connected=connected,
            inventory_path=str(self.runtime_inventory_path.resolve()),
            last_error=None if port_open else self._last_error,
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
            self._prepare_vehicle_for_command(command)
            method = getattr(self._client, method_name)
            result = self._call_with_vehicle_fallback(method, *args)
            if hasattr(result, "join"):
                result.join()
            if command == "land":
                try:
                    self._call_with_vehicle_fallback(self._client.armDisarm, False)
                except Exception:
                    pass
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

    def _prepare_vehicle_for_command(self, command: str) -> None:
        if self._client is None:
            raise RuntimeError("Simulated drone runtime is disconnected.")
        if hasattr(self._client, "enableApiControl"):
            self._call_with_vehicle_fallback(self._client.enableApiControl, True)
        if command != "land" and hasattr(self._client, "armDisarm"):
            self._call_with_vehicle_fallback(self._client.armDisarm, True)

    def get_drone_state(self) -> dict[str, Any]:
        telemetry = self.get_telemetry()
        return telemetry.model_dump(mode="json")

    def _normalize_camera_name(self, camera_name: str) -> str:
        name = str(camera_name or "").strip().lower()
        if not name:
            name = self.camera_name
        if name not in self.allowed_cameras:
            raise ValueError(
                f"Unsupported camera '{camera_name}'. Supported cameras: {', '.join(self.allowed_cameras)}"
            )
        return name

    def _runtime_name_hint(self) -> str | None:
        status = self.get_city_runtime_status()
        if status.selected_runtime:
            self.city_runtime = status.selected_runtime
        return status.selected_runtime

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

    def _call_with_vehicle_fallback(self, method: Any, *args: Any) -> Any:
        if self._supports_named_vehicle_calls is False:
            return self._call(method, *args)
        try:
            result = self._call(method, *args, vehicle_name=self.vehicle_name)
            self._supports_named_vehicle_calls = True
            return result
        except Exception as exc:
            if not self._supports_vehicle_fallback(exc):
                raise
            logger.warning(
                "Cosys-AirSim rejected named vehicle '%s'; retrying RPC without vehicle_name.",
                self.vehicle_name,
            )
            self._supports_named_vehicle_calls = False
            return self._call(method, *args)

    def _supports_vehicle_fallback(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            ("vehicle api for" in message and "not available" in message)
            or "vehicle does not exist" in message
            or "retry connection over the limit" in message
        )

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
