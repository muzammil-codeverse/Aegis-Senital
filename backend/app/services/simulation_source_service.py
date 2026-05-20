from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.simulation_source_models import (
    CityCamera,
    CityDrone,
    CityLocation,
    CameraOrientation,
    CameraCoverage,
    DashboardFeedEntry,
    SimCameraStatus,
    SimDroneStatus,
    SimSourceType,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_PERSISTENCE_PATH = _PROJECT_ROOT / "runtime_state" / "simulation_sources.json"

MIN_CAMERAS_THRESHOLD = 12
MIN_DRONES_THRESHOLD = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Default seed data — 16 simulated city cameras + 3 drones
# ---------------------------------------------------------------------------

_DEFAULT_CAMERAS: list[dict[str, Any]] = [
    # Zone 1: Financial District / Bank (3 cameras)
    {
        "camera_id": "CAM-BANK-01",
        "name": "Bank Main Entrance",
        "source_type": "fixed_cctv",
        "zone_id": "zone_financial",
        "zone_name": "Financial District",
        "district": "financial",
        "location": {"x": 120.0, "y": 80.0, "z": 3.5},
        "orientation": {"yaw": 180.0, "pitch": -15.0},
        "coverage": {"range_meters": 30.0, "fov_degrees": 90.0, "direction": "south"},
        "feed_uri": "simulation://city/bank/entrance",
        "status": "online",
        "priority": "critical",
        "supported_detections": ["weapon", "person", "suspicious_person", "zone_intrusion"],
        "linked_scenarios": ["bank_robbery"],
        "dashboard_pinned": True,
        "metadata": {"simulated": True, "floor": 0, "description": "Primary bank entrance monitoring — high priority"},
    },
    {
        "camera_id": "CAM-BANK-02",
        "name": "Bank Interior Vault Corridor",
        "source_type": "fixed_cctv",
        "zone_id": "zone_financial",
        "zone_name": "Financial District",
        "district": "financial",
        "location": {"x": 145.0, "y": 100.0, "z": 3.0},
        "orientation": {"yaw": 90.0},
        "coverage": {"range_meters": 20.0, "fov_degrees": 60.0, "direction": "east"},
        "feed_uri": "simulation://city/bank/interior",
        "status": "online",
        "priority": "critical",
        "supported_detections": ["weapon", "person", "suspicious_person"],
        "linked_scenarios": ["bank_robbery"],
        "dashboard_pinned": True,
        "metadata": {"simulated": True, "floor": 0, "description": "Vault corridor access control camera"},
    },
    {
        "camera_id": "CAM-BANK-03",
        "name": "Bank ATM Zone",
        "source_type": "ptz_camera",
        "zone_id": "zone_financial",
        "zone_name": "Financial District",
        "district": "financial",
        "location": {"x": 105.0, "y": 70.0, "z": 4.0},
        "orientation": {"yaw": 270.0, "pitch": -20.0},
        "coverage": {"range_meters": 25.0, "fov_degrees": 110.0, "direction": "west"},
        "feed_uri": "simulation://city/bank/atm",
        "status": "online",
        "priority": "high",
        "supported_detections": ["weapon", "person"],
        "linked_scenarios": ["bank_robbery"],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "floor": 0, "description": "PTZ camera covering ATM cluster"},
    },
    # Zone 2: Main Road (2 cameras)
    {
        "camera_id": "CAM-ROAD-01",
        "name": "Main Road North Intersection",
        "source_type": "fixed_cctv",
        "zone_id": "zone_main_road",
        "zone_name": "Main Road",
        "district": "central",
        "location": {"x": 300.0, "y": 50.0, "z": 5.0},
        "orientation": {"yaw": 0.0},
        "coverage": {"range_meters": 80.0, "fov_degrees": 120.0, "direction": "north"},
        "feed_uri": "simulation://city/road/north",
        "status": "online",
        "priority": "high",
        "supported_detections": ["vehicle", "person", "suspicious_person"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Traffic monitoring — north approach"},
    },
    {
        "camera_id": "CAM-ROAD-02",
        "name": "Main Road South Junction",
        "source_type": "fixed_cctv",
        "zone_id": "zone_main_road",
        "zone_name": "Main Road",
        "district": "central",
        "location": {"x": 300.0, "y": 400.0, "z": 5.0},
        "orientation": {"yaw": 180.0},
        "coverage": {"range_meters": 80.0, "fov_degrees": 120.0, "direction": "south"},
        "feed_uri": "simulation://city/road/south",
        "status": "online",
        "priority": "normal",
        "supported_detections": ["vehicle", "person"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Traffic monitoring — south approach"},
    },
    # Zone 3: Market District (2 cameras)
    {
        "camera_id": "CAM-MARKET-01",
        "name": "Central Market Plaza",
        "source_type": "ptz_camera",
        "zone_id": "zone_market",
        "zone_name": "Market District",
        "district": "market",
        "location": {"x": 500.0, "y": 200.0, "z": 6.0},
        "orientation": {"yaw": 45.0, "pitch": -25.0},
        "coverage": {"range_meters": 60.0, "fov_degrees": 110.0, "direction": "northeast"},
        "feed_uri": "simulation://city/market/plaza",
        "status": "online",
        "priority": "high",
        "supported_detections": ["person", "suspicious_person", "crowd_anomaly"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Wide-area PTZ coverage of market plaza"},
    },
    {
        "camera_id": "CAM-MARKET-02",
        "name": "Market Perimeter Fence",
        "source_type": "fixed_cctv",
        "zone_id": "zone_market",
        "zone_name": "Market District",
        "district": "market",
        "location": {"x": 560.0, "y": 180.0, "z": 3.0},
        "orientation": {"yaw": 315.0},
        "coverage": {"range_meters": 45.0, "fov_degrees": 90.0, "direction": "northwest"},
        "feed_uri": "simulation://city/market/perimeter",
        "status": "online",
        "priority": "normal",
        "supported_detections": ["person", "zone_intrusion"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Perimeter monitoring — northwest fence"},
    },
    # Zone 4: Residential Block (2 cameras)
    {
        "camera_id": "CAM-RESIDENTIAL-01",
        "name": "Residential Block A Entrance",
        "source_type": "fixed_cctv",
        "zone_id": "zone_residential",
        "zone_name": "Residential Block",
        "district": "residential",
        "location": {"x": 650.0, "y": 300.0, "z": 3.0},
        "orientation": {"yaw": 270.0},
        "coverage": {"range_meters": 35.0, "fov_degrees": 80.0, "direction": "west"},
        "feed_uri": "simulation://city/residential/block_a",
        "status": "online",
        "priority": "normal",
        "supported_detections": ["person", "suspicious_person"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Residential Block A entry/exit"},
    },
    {
        "camera_id": "CAM-RESIDENTIAL-02",
        "name": "Residential Block B Pathway",
        "source_type": "fixed_cctv",
        "zone_id": "zone_residential",
        "zone_name": "Residential Block",
        "district": "residential",
        "location": {"x": 700.0, "y": 350.0, "z": 3.0},
        "orientation": {"yaw": 90.0},
        "coverage": {"range_meters": 30.0, "fov_degrees": 80.0, "direction": "east"},
        "feed_uri": "simulation://city/residential/block_b",
        "status": "degraded",
        "priority": "normal",
        "supported_detections": ["person"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Residential Block B pathway — minor occlusion reported"},
    },
    # Zone 5: Parking Area (1 camera)
    {
        "camera_id": "CAM-PARKING-01",
        "name": "Parking Lot North",
        "source_type": "ptz_camera",
        "zone_id": "zone_parking",
        "zone_name": "Parking Area",
        "district": "central",
        "location": {"x": 400.0, "y": 500.0, "z": 8.0},
        "orientation": {"yaw": 135.0, "pitch": -30.0},
        "coverage": {"range_meters": 70.0, "fov_degrees": 130.0, "direction": "southeast"},
        "feed_uri": "simulation://city/parking/north",
        "status": "online",
        "priority": "normal",
        "supported_detections": ["vehicle", "person", "suspicious_person"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Elevated PTZ covering main parking area"},
    },
    # Zone 6: Society Gate / Entry-Exit (2 cameras)
    {
        "camera_id": "CAM-GATE-01",
        "name": "Main Gate Entry",
        "source_type": "fixed_cctv",
        "zone_id": "zone_gate",
        "zone_name": "Society Gate",
        "district": "perimeter",
        "location": {"x": 0.0, "y": 250.0, "z": 4.0},
        "orientation": {"yaw": 0.0},
        "coverage": {"range_meters": 40.0, "fov_degrees": 90.0, "direction": "north"},
        "feed_uri": "simulation://city/gate/entry",
        "status": "online",
        "priority": "high",
        "supported_detections": ["vehicle", "person", "weapon"],
        "linked_scenarios": [],
        "dashboard_pinned": True,
        "metadata": {"simulated": True, "description": "Primary city perimeter entry gate"},
    },
    {
        "camera_id": "CAM-GATE-02",
        "name": "Main Gate Exit",
        "source_type": "fixed_cctv",
        "zone_id": "zone_gate",
        "zone_name": "Society Gate",
        "district": "perimeter",
        "location": {"x": 0.0, "y": 270.0, "z": 4.0},
        "orientation": {"yaw": 180.0},
        "coverage": {"range_meters": 40.0, "fov_degrees": 90.0, "direction": "south"},
        "feed_uri": "simulation://city/gate/exit",
        "status": "online",
        "priority": "high",
        "supported_detections": ["vehicle", "person"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Primary city perimeter exit gate"},
    },
    # Zone 7: Rooftop / High View (1 camera)
    {
        "camera_id": "CAM-ROOF-01",
        "name": "Financial District Rooftop Overview",
        "source_type": "simulation_virtual_camera",
        "zone_id": "zone_rooftop",
        "zone_name": "Rooftop Overview",
        "district": "financial",
        "location": {"x": 200.0, "y": 150.0, "z": 30.0},
        "orientation": {"yaw": 0.0, "pitch": -60.0},
        "coverage": {"range_meters": 200.0, "fov_degrees": 150.0, "direction": "north"},
        "feed_uri": "simulation://city/rooftop/financial_overview",
        "status": "online",
        "priority": "high",
        "supported_detections": ["person", "vehicle", "drone_observation"],
        "linked_scenarios": ["bank_robbery"],
        "dashboard_pinned": True,
        "metadata": {"simulated": True, "description": "Elevated bird-eye view of financial district"},
    },
    # Zone 8: Park / Open Area (1 camera)
    {
        "camera_id": "CAM-PARK-01",
        "name": "City Park Central",
        "source_type": "fixed_cctv",
        "zone_id": "zone_park",
        "zone_name": "City Park",
        "district": "central",
        "location": {"x": 450.0, "y": 320.0, "z": 4.0},
        "orientation": {"yaw": 225.0},
        "coverage": {"range_meters": 50.0, "fov_degrees": 100.0, "direction": "southwest"},
        "feed_uri": "simulation://city/park/central",
        "status": "online",
        "priority": "low",
        "supported_detections": ["person", "crowd_anomaly"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Open area crowd monitoring"},
    },
    # Zone 9: School / Public Building (1 camera)
    {
        "camera_id": "CAM-SCHOOL-01",
        "name": "Public School Main Entrance",
        "source_type": "fixed_cctv",
        "zone_id": "zone_public",
        "zone_name": "Public Buildings",
        "district": "residential",
        "location": {"x": 750.0, "y": 180.0, "z": 3.5},
        "orientation": {"yaw": 180.0},
        "coverage": {"range_meters": 35.0, "fov_degrees": 90.0, "direction": "south"},
        "feed_uri": "simulation://city/school/entrance",
        "status": "online",
        "priority": "high",
        "supported_detections": ["person", "weapon", "suspicious_person"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "School perimeter safety monitoring"},
    },
    # Zone 10: Alley / Blind Spot (1 camera)
    {
        "camera_id": "CAM-ALLEY-01",
        "name": "East Alley Blind Spot",
        "source_type": "fixed_cctv",
        "zone_id": "zone_alley",
        "zone_name": "Alley Network",
        "district": "central",
        "location": {"x": 250.0, "y": 340.0, "z": 3.0},
        "orientation": {"yaw": 90.0},
        "coverage": {"range_meters": 20.0, "fov_degrees": 60.0, "direction": "east"},
        "feed_uri": "simulation://city/alley/east",
        "status": "online",
        "priority": "normal",
        "supported_detections": ["person", "suspicious_person", "weapon"],
        "linked_scenarios": [],
        "dashboard_pinned": False,
        "metadata": {"simulated": True, "description": "Narrow alley — limited visibility corridor"},
    },
]

_DEFAULT_DRONES: list[dict[str, Any]] = [
    {
        "drone_id": "DRONE-ALPHA",
        "name": "Alpha — Financial District Rapid Response",
        "status": "standby",
        "assigned_zone": "zone_financial",
        "current_location": {"x": 130.0, "y": 90.0, "z": 10.0},
        "home_location": {"x": 130.0, "y": 90.0, "z": 0.0},
        "camera_feed_uri": "simulation://drone/alpha/feed",
        "battery_percent": 100.0,
        "capabilities": ["hd_video", "thermal", "zoom_10x", "autonomous_tracking"],
        "metadata": {
            "simulated": True,
            "model": "AegisQuad-X4",
            "max_speed_mps": 15.0,
            "endurance_minutes": 40,
            "description": "Rapid response drone assigned to financial district; bank robbery scenario primary responder",
        },
    },
    {
        "drone_id": "DRONE-BRAVO",
        "name": "Bravo — Residential and Gate Patrol",
        "status": "standby",
        "assigned_zone": "zone_residential",
        "current_location": {"x": 650.0, "y": 260.0, "z": 8.0},
        "home_location": {"x": 650.0, "y": 260.0, "z": 0.0},
        "camera_feed_uri": "simulation://drone/bravo/feed",
        "battery_percent": 87.0,
        "capabilities": ["hd_video", "zoom_5x", "perimeter_patrol"],
        "metadata": {
            "simulated": True,
            "model": "AegisQuad-X3",
            "max_speed_mps": 12.0,
            "endurance_minutes": 35,
            "description": "Residential block and gate patrol; secondary responder for perimeter incidents",
        },
    },
    {
        "drone_id": "DRONE-CHARLIE",
        "name": "Charlie — Reserve High-Altitude Overview",
        "status": "charging",
        "assigned_zone": "zone_rooftop",
        "current_location": {"x": 400.0, "y": 250.0, "z": 0.0},
        "home_location": {"x": 400.0, "y": 250.0, "z": 0.0},
        "camera_feed_uri": "simulation://drone/charlie/feed",
        "battery_percent": 62.0,
        "capabilities": ["hd_video", "thermal", "zoom_20x", "wide_area_survey"],
        "metadata": {
            "simulated": True,
            "model": "AegisFixed-F1",
            "max_speed_mps": 20.0,
            "endurance_minutes": 60,
            "description": "Reserve drone; high-altitude city-wide overview and thermal imaging capability",
        },
    },
]


class CitySurveillanceRegistry:
    """
    Registry for simulated city surveillance cameras and drone assets.
    Persists source state to JSON for stability across restarts.
    """

    def __init__(self, persistence_path: Path | str | None = None) -> None:
        self._lock = threading.RLock()
        self._cameras: dict[str, CityCamera] = {}
        self._drones: dict[str, CityDrone] = {}
        self._persistence_path = Path(persistence_path) if persistence_path else _DEFAULT_PERSISTENCE_PATH
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()

    def _load(self) -> None:
        loaded_cameras: dict[str, CityCamera] = {}
        loaded_drones: dict[str, CityDrone] = {}

        if self._persistence_path.exists():
            try:
                payload = json.loads(self._persistence_path.read_text(encoding="utf-8"))
                for item in payload.get("cameras") or []:
                    cam = CityCamera.from_dict(item)
                    loaded_cameras[cam.camera_id] = cam
                for item in payload.get("drones") or []:
                    drone = CityDrone.from_dict(item)
                    loaded_drones[drone.drone_id] = drone
                logger.info(
                    "Simulation registry loaded from %s: %d cameras, %d drones",
                    self._persistence_path, len(loaded_cameras), len(loaded_drones),
                )
            except Exception as exc:
                logger.warning("Failed to load simulation sources from %s: %s", self._persistence_path, exc)

        # Seed any cameras not yet persisted
        for cam_dict in _DEFAULT_CAMERAS:
            cam_id = cam_dict["camera_id"]
            if cam_id not in loaded_cameras:
                loaded_cameras[cam_id] = CityCamera.from_dict(cam_dict)

        for drone_dict in _DEFAULT_DRONES:
            drone_id = drone_dict["drone_id"]
            if drone_id not in loaded_drones:
                loaded_drones[drone_id] = CityDrone.from_dict(drone_dict)

        with self._lock:
            self._cameras = loaded_cameras
            self._drones = loaded_drones
            self._loaded = True

        self._persist()
        logger.info(
            "Simulation city registry ready: %d cameras, %d drones",
            len(self._cameras), len(self._drones),
        )

    def _persist(self) -> None:
        try:
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = {
                    "cameras": [c.to_dict() for c in self._cameras.values()],
                    "drones": [d.to_dict() for d in self._drones.values()],
                }
            self._persistence_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning("Failed to persist simulation sources: %s", exc)

    # ------------------------------------------------------------------
    # Camera operations
    # ------------------------------------------------------------------

    def list_cameras(self, zone_id: str | None = None) -> list[CityCamera]:
        self._ensure_loaded()
        with self._lock:
            cameras = list(self._cameras.values())
        if zone_id:
            cameras = [c for c in cameras if c.zone_id == zone_id]
        return cameras

    def list_active_cameras(self) -> list[CityCamera]:
        self._ensure_loaded()
        with self._lock:
            return [c for c in self._cameras.values() if c.status == SimCameraStatus.ONLINE]

    def get_camera(self, camera_id: str) -> CityCamera | None:
        self._ensure_loaded()
        with self._lock:
            return self._cameras.get(camera_id)

    def update_camera_status(self, camera_id: str, status: SimCameraStatus, reason: str | None = None) -> CityCamera | None:
        self._ensure_loaded()
        with self._lock:
            camera = self._cameras.get(camera_id)
            if camera is None:
                return None
            camera.status = status
            camera.updated_at = _now_iso()
            if reason:
                camera.metadata["last_status_reason"] = reason
        self._persist()
        return camera

    def mark_observation(self, camera_id: str) -> None:
        self._ensure_loaded()
        with self._lock:
            camera = self._cameras.get(camera_id)
            if camera:
                camera.last_observation_at = _now_iso()

    # ------------------------------------------------------------------
    # Drone operations
    # ------------------------------------------------------------------

    def list_drones(self) -> list[CityDrone]:
        self._ensure_loaded()
        with self._lock:
            return list(self._drones.values())

    def get_drone(self, drone_id: str) -> CityDrone | None:
        self._ensure_loaded()
        with self._lock:
            return self._drones.get(drone_id)

    def update_drone_status(self, drone_id: str, status: SimDroneStatus, reason: str | None = None) -> CityDrone | None:
        self._ensure_loaded()
        with self._lock:
            drone = self._drones.get(drone_id)
            if drone is None:
                return None
            drone.status = status
            drone.updated_at = _now_iso()
            if reason:
                drone.metadata["last_status_reason"] = reason
        self._persist()
        return drone

    # ------------------------------------------------------------------
    # Dashboard feed list
    # ------------------------------------------------------------------

    def dashboard_feed_list(self) -> list[DashboardFeedEntry]:
        self._ensure_loaded()
        with self._lock:
            cameras = list(self._cameras.values())
        # Pinned cameras first, then by priority
        priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        cameras.sort(
            key=lambda c: (0 if c.dashboard_pinned else 1, priority_order.get(c.priority, 9))
        )
        return [
            DashboardFeedEntry(
                camera_id=c.camera_id,
                name=c.name,
                zone_id=c.zone_id,
                zone_name=c.zone_name,
                district=c.district,
                location=c.location,
                orientation=c.orientation,
                coverage=c.coverage,
                status=c.status,
                source_type=c.source_type,
                feed_uri=c.feed_uri,
                priority=c.priority,
                supported_detections=list(c.supported_detections),
                dashboard_pinned=c.dashboard_pinned,
                last_observation_at=c.last_observation_at,
                metadata={**c.metadata},
            )
            for c in cameras
        ]

    # ------------------------------------------------------------------
    # Source governance — validate observation source IDs
    # ------------------------------------------------------------------

    def validate_camera_source(self, camera_id: str) -> tuple[bool, str]:
        self._ensure_loaded()
        camera = self.get_camera(camera_id)
        if camera is None:
            return False, f"Camera source '{camera_id}' is not registered in the city surveillance network"
        return True, camera.zone_id

    def validate_drone_source(self, drone_id: str) -> tuple[bool, str]:
        self._ensure_loaded()
        drone = self.get_drone(drone_id)
        if drone is None:
            return False, f"Drone source '{drone_id}' is not registered in the city surveillance network"
        return True, drone.assigned_zone

    def source_metadata(self, *, camera_id: str | None = None, drone_id: str | None = None) -> dict[str, Any]:
        """Return source-enrichment metadata for intelligence events."""
        self._ensure_loaded()
        meta: dict[str, Any] = {"simulated": True}
        if camera_id:
            camera = self.get_camera(camera_id)
            if camera:
                meta.update({
                    "camera_id": camera.camera_id,
                    "camera_name": camera.name,
                    "zone_id": camera.zone_id,
                    "zone_name": camera.zone_name,
                    "district": camera.district,
                    "source_type": camera.source_type.value,
                    "feed_uri": camera.feed_uri,
                })
        if drone_id:
            drone = self.get_drone(drone_id)
            if drone:
                meta.update({
                    "drone_id": drone.drone_id,
                    "drone_name": drone.name,
                    "assigned_zone": drone.assigned_zone,
                    "drone_source_type": "drone_camera",
                })
        return meta

    # ------------------------------------------------------------------
    # Health snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        self._ensure_loaded()
        with self._lock:
            cameras = list(self._cameras.values())
            drones = list(self._drones.values())
        return {
            "camera_count": len(cameras),
            "drone_count": len(drones),
            "cameras_online": sum(1 for c in cameras if c.status == SimCameraStatus.ONLINE),
            "cameras_offline": sum(1 for c in cameras if c.status == SimCameraStatus.OFFLINE),
            "cameras_degraded": sum(1 for c in cameras if c.status == SimCameraStatus.DEGRADED),
            "drones_standby": sum(1 for d in drones if d.status == SimDroneStatus.STANDBY),
            "drones_airborne": sum(1 for d in drones if d.status == SimDroneStatus.AIRBORNE),
            "zones": sorted({c.zone_id for c in cameras}),
            "source_network_ready": len(cameras) >= MIN_CAMERAS_THRESHOLD and len(drones) >= MIN_DRONES_THRESHOLD,
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_registry: CitySurveillanceRegistry | None = None
_registry_lock = threading.Lock()


def get_city_surveillance_registry() -> CitySurveillanceRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = CitySurveillanceRegistry()
    return _registry
