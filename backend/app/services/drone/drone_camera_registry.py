from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.camera_models import CameraSourceType, CameraStatus
from app.services.camera_registry import CameraRegistry


SUPPORTED_DRONE_CAMERAS = (
    "front_center",
    "front_left",
    "front_right",
    "downward",
    "rear",
)


@dataclass(frozen=True, slots=True)
class DroneCameraSource:
    source_id: str
    drone_id: str
    camera_name: str
    source_type: str = "drone_simulation"
    simulated: bool = True
    operator_review_required: bool = True

    def to_metadata(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "drone_id": self.drone_id,
            "camera_name": self.camera_name,
            "simulated": self.simulated,
            "operator_review_required": self.operator_review_required,
            "safety_badge": "Simulated drone feed",
        }


def build_drone_source_id(drone_id: str, camera_name: str) -> str:
    return f"{drone_id}_{camera_name}"


def is_supported_camera(camera_name: str) -> bool:
    return str(camera_name).strip().lower() in SUPPORTED_DRONE_CAMERAS


def list_drone_camera_sources(drone_id: str = "drone_sim_01") -> list[DroneCameraSource]:
    return [
        DroneCameraSource(
            source_id=build_drone_source_id(drone_id, camera_name),
            drone_id=drone_id,
            camera_name=camera_name,
        )
        for camera_name in SUPPORTED_DRONE_CAMERAS
    ]


def register_drone_camera_sources(
    registry: CameraRegistry,
    *,
    drone_id: str = "drone_sim_01",
    host: str = "127.0.0.1",
    port: int = 41451,
    vehicle_name: str = "Drone1",
    default_fov: float = 90.0,
) -> None:
    for source in list_drone_camera_sources(drone_id):
        camera_id = source.source_id
        camera = registry.get_camera(camera_id)
        source_uri = f"cosys_airsim://{host}:{port}/{vehicle_name}/{source.camera_name}"
        metadata = source.to_metadata()
        if camera is None:
            try:
                registry.register_camera(
                    {
                        "camera_id": camera_id,
                        "name": f"Drone {source.camera_name.replace('_', ' ').title()}",
                        "source_type": CameraSourceType.DRONE_SIM.value,
                        "source_uri": source_uri,
                        "status": CameraStatus.OFFLINE.value,
                        "enabled": True,
                        "fov_degrees": default_fov if source.camera_name != "downward" else 110.0,
                        "coverage_radius": 150,
                        "location": {"region": "simulated_airspace"},
                        "zone": "simulated_airspace",
                        "metadata": metadata,
                    }
                )
            except ValueError:
                continue
        else:
            merged = {**dict(camera.metadata or {}), **metadata}
            registry.update_camera(
                camera_id,
                {
                    "name": camera.name or f"Drone {source.camera_name}",
                    "source_uri": source_uri,
                    "enabled": True,
                    "metadata": merged,
                },
            )
