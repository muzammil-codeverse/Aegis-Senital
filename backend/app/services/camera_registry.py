from __future__ import annotations

import logging
import threading
import time

from app.models.camera_models import Camera, CameraStatus
from inference.config_runtime import load_runtime_config

logger = logging.getLogger(__name__)

_MAX_CAMERAS_DEFAULT = 128


class CameraRegistry:
    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self._lock = threading.RLock()
        self._cameras: dict[str, Camera] = {}
        self._max_cameras: int = int(cfg.get("max_cameras", _MAX_CAMERAS_DEFAULT))

    def register_camera(self, camera_config: dict) -> Camera:
        camera = Camera.from_dict(camera_config)
        with self._lock:
            if len(self._cameras) >= self._max_cameras:
                raise RuntimeError(f"Camera registry full (max {self._max_cameras})")
            if camera.camera_id in self._cameras:
                raise ValueError(f"Camera '{camera.camera_id}' already registered")
            camera.created_at = time.time()
            camera.updated_at = time.time()
            self._cameras[camera.camera_id] = camera
        logger.info("Camera registered: %s", camera.camera_id)
        return camera

    def update_camera(self, camera_id: str, updates: dict) -> Camera | None:
        _immutable = {"camera_id", "created_at"}
        with self._lock:
            camera = self._cameras.get(camera_id)
            if camera is None:
                return None
            for key, value in updates.items():
                if key not in _immutable and hasattr(camera, key):
                    setattr(camera, key, value)
            camera.updated_at = time.time()
        return camera

    def remove_camera(self, camera_id: str) -> bool:
        with self._lock:
            if camera_id not in self._cameras:
                return False
            del self._cameras[camera_id]
        logger.info("Camera removed: %s", camera_id)
        return True

    def get_camera(self, camera_id: str) -> Camera | None:
        with self._lock:
            return self._cameras.get(camera_id)

    def list_cameras(
        self,
        status: str | None = None,
        enabled: bool | None = None,
    ) -> list[Camera]:
        with self._lock:
            cameras = list(self._cameras.values())
        if status is not None:
            cameras = [c for c in cameras if c.status == status.lower()]
        if enabled is not None:
            cameras = [c for c in cameras if c.enabled == enabled]
        return cameras

    def set_camera_status(
        self,
        camera_id: str,
        status: str,
        reason: str | None = None,
    ) -> Camera | None:
        with self._lock:
            camera = self._cameras.get(camera_id)
            if camera is None:
                return None
            camera.status = status.lower()
            camera.updated_at = time.time()
            if reason:
                camera.metadata["last_status_reason"] = reason
        return camera

    def mark_frame_seen(self, camera_id: str, timestamp: float | None = None) -> None:
        ts = timestamp or time.time()
        with self._lock:
            camera = self._cameras.get(camera_id)
            if camera is None:
                return
            camera.last_frame_at = ts
            camera.updated_at = ts
            if camera.status in (CameraStatus.OFFLINE.value, CameraStatus.DISABLED.value):
                camera.status = CameraStatus.ONLINE.value

    def mark_event_seen(self, camera_id: str, timestamp: float | None = None) -> None:
        ts = timestamp or time.time()
        with self._lock:
            camera = self._cameras.get(camera_id)
            if camera is None:
                return
            camera.last_event_at = ts
            camera.updated_at = ts

    def load_from_config(self) -> None:
        try:
            config = load_runtime_config("cameras")
        except (FileNotFoundError, Exception) as exc:
            logger.warning("Could not load cameras.yaml: %s", exc)
            return
        self._max_cameras = int(config.get("max_cameras", _MAX_CAMERAS_DEFAULT))
        cameras_config = config.get("cameras") or []
        loaded = 0
        for cam_cfg in cameras_config:
            if not isinstance(cam_cfg, dict) or not cam_cfg.get("camera_id"):
                continue
            try:
                with self._lock:
                    if cam_cfg["camera_id"] not in self._cameras:
                        self.register_camera(cam_cfg)
                        loaded += 1
            except Exception as exc:
                logger.warning("Failed to load camera %s: %s", cam_cfg.get("camera_id"), exc)
        logger.info("Camera registry loaded %d cameras from config", loaded)

    def snapshot(self) -> dict:
        with self._lock:
            cameras = list(self._cameras.values())
        return {
            "total": len(cameras),
            "online": sum(1 for c in cameras if c.status == CameraStatus.ONLINE.value),
            "offline": sum(1 for c in cameras if c.status == CameraStatus.OFFLINE.value),
            "degraded": sum(1 for c in cameras if c.status == CameraStatus.DEGRADED.value),
            "error": sum(1 for c in cameras if c.status == CameraStatus.ERROR.value),
            "disabled": sum(1 for c in cameras if c.status == CameraStatus.DISABLED.value),
            "enabled": sum(1 for c in cameras if c.enabled),
            "max_cameras": self._max_cameras,
        }


_registry: CameraRegistry | None = None
_registry_lock = threading.Lock()


def get_camera_registry() -> CameraRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = CameraRegistry()
                _registry.load_from_config()
    return _registry
