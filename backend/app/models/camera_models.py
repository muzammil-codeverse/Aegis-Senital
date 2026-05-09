from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CameraStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    ERROR = "error"
    DISABLED = "disabled"


class CameraSourceType(str, Enum):
    RTSP = "rtsp"
    WEBCAM = "webcam"
    VIDEO_FILE = "video_file"
    DRONE_SIM = "drone_sim"
    MOCK = "mock"


class CameraPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Camera:
    camera_id: str
    name: str
    source_type: str = field(default=CameraSourceType.MOCK.value)
    source_uri: str | None = None
    location: dict | None = None
    zone: str | None = None
    priority: str = field(default=CameraPriority.NORMAL.value)
    status: str = field(default=CameraStatus.OFFLINE.value)
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_frame_at: float | None = None
    last_event_at: float | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "name": self.name,
            "source_type": self.source_type,
            "source_uri": self.source_uri,
            "location": self.location or {},
            "zone": self.zone,
            "priority": self.priority,
            "status": self.status,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_frame_at": self.last_frame_at,
            "last_event_at": self.last_event_at,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Camera":
        return cls(
            camera_id=str(data["camera_id"]),
            name=str(data.get("name") or data["camera_id"]),
            source_type=str(data.get("source_type") or CameraSourceType.MOCK.value).lower(),
            source_uri=data.get("source_uri") or None,
            location=data.get("location") or None,
            zone=data.get("zone") or None,
            priority=str(data.get("priority") or CameraPriority.NORMAL.value).lower(),
            status=str(data.get("status") or CameraStatus.OFFLINE.value).lower(),
            enabled=bool(data.get("enabled", True)),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            last_frame_at=data.get("last_frame_at") or None,
            last_event_at=data.get("last_event_at") or None,
            metadata=dict(data.get("metadata") or {}),
        )
