"""
AegisVisualScenarioController — Phase XI + Phase XII Visual Simulation Bridge.

Phase XI delivered the proxy-overlay layer:
  * Zone boundary rectangles
  * Actor proxy markers
  * Camera zone diamonds
  * Crime-scene event markers
  * DRONE-ALPHA route polyline
  * Animated movement along Phase 6/7 waypoints

Phase XII upgrades the controller to render *visually convincing* actors and
expose the visuals to the rest of the platform:

  * Humanoid proxy stacks (body + head spheres) for human actors so the
    silhouette reads as a person, not a flat dot.
  * Vehicle proxy rectangles (4 corners + roof point) for vehicle actors.
  * Live `simListAssets` / `simSpawnObject` probing so that, when the
    packaged binary exposes real mesh assets, the controller spawns and
    re-poses real 3D meshes instead of debug markers.
  * `simGetImages` snapshot capture from the drone camera and from any
    AirSim ExternalCameras present in the scene, written to
    runtime_state/visual_snapshots/{camera_id}.png.
  * sync_to_offset(t_offset_seconds) so the backend scenario engine can
    drive the visual clock at every demo step.
  * real_actor_mode reporting (real_mesh / spawned_mesh / proxy_overlay /
    unavailable) so the dashboard can honestly display the current visual
    fidelity.

Coordinate convention
---------------------
Scenario JSON uses (x=north, y=east, z=altitude_up). AirSim NED uses
(x=north, y=east, z=DOWN). Helpers negate z when building AirSim Vector3r.

Public entry points (added in Phase XII are marked NEW):

    setup_static_scene()        — Phase XI
    run_animation(duration)     — Phase XI (blocking)
    start_animation_thread()    — Phase XI (background)
    stop_animation()            — Phase XI
    flush_markers()             — Phase XI

    sync_to_offset(t)           — NEW Phase XII
    capture_camera_snapshot(id) — NEW Phase XII
    capture_all_snapshots()     — NEW Phase XII
    probe_real_actor_mode()     — NEW Phase XII
    get_status()                — extended with real_actor_mode etc.
"""

from __future__ import annotations

import json
import logging
import math
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_VISUAL_JSON = (
    _PROJECT_ROOT
    / "simulation"
    / "visual_scenarios"
    / "bank_robbery_visual.json"
)
_SNAPSHOT_DIR = _PROJECT_ROOT / "runtime_state" / "visual_snapshots"

# Asset name hints we look for in simListAssets() output. None of these are
# guaranteed to exist; the controller treats absence as "no real mesh".
_HUMAN_MESH_HINTS = (
    "SK_Mannequin",
    "Mannequin",
    "Character",
    "Pedestrian",
    "MetaHuman",
    "Crowd",
)
_VEHICLE_MESH_HINTS = (
    "SUV",
    "Sedan",
    "Car",
    "Vehicle",
    "Hatchback",
    "Pickup",
    "Truck",
)
_PROP_MESH_HINTS = (
    "Cone",
    "Barrier",
    "TrafficSign",
    "Sign",
    "Bollard",
)


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0  # altitude above ground (positive up) in scenario coords

    def airsim_z(self) -> float:
        """Return NED z (down-positive) for AirSim."""
        return -self.z


@dataclass
class _Actor:
    actor_id: str
    label: str
    color: list[float]
    size: float
    role: str
    current_pose: _Vec3
    waypoints: list[dict[str, Any]] = field(default_factory=list)
    group_members: list[_Vec3] = field(default_factory=list)
    active: bool = True
    spawned_object_name: str | None = None


@dataclass
class _VisualState:
    elapsed: float = 0.0
    running: bool = False
    static_drawn: bool = False
    crime_markers_active: set[str] = field(default_factory=set)
    real_actor_mode: str = "unavailable"
    spawned_assets: dict[str, str] = field(default_factory=dict)
    last_snapshot_at: dict[str, str] = field(default_factory=dict)
    last_sync_offset_seconds: float | None = None


# ---------------------------------------------------------------------------
# AirSim module loader (mirrors cosys_airsim_client.py approach)
# ---------------------------------------------------------------------------

def _load_airsim_module() -> Any | None:
    for module_name in ("cosysairsim", "airsim"):
        try:
            return __import__(module_name)
        except ImportError:
            continue
    pyclient_dir = os.environ.get(
        "AEGIS_COSYS_AIRSIM_PYTHONCLIENT_DIR",
        r"C:\AegisExternalTools\drone_sim\cosys_airsim\Cosys-AirSim\PythonClient",
    )
    if pyclient_dir and Path(pyclient_dir).exists():
        if pyclient_dir not in sys.path:
            sys.path.insert(0, pyclient_dir)
        for module_name in ("cosysairsim", "airsim"):
            try:
                return __import__(module_name)
            except ImportError:
                continue
    return None


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class AegisVisualScenarioController:
    """
    Renders the bank_robbery_demo visual world in a running AirSim instance.

    All public methods degrade gracefully if AirSim is unavailable — they
    log a warning and return a status dict rather than raising.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        vehicle_name: str | None = None,
        visual_json_path: Path | str | None = None,
        real_time_factor: float = 1.0,
        dry_run: bool = False,
        snapshot_dir: Path | str | None = None,
    ) -> None:
        self._host = str(host or os.environ.get("AEGIS_AIRSIM_HOST") or "127.0.0.1")
        self._port = int(port or os.environ.get("AEGIS_AIRSIM_PORT") or 41451)
        self._vehicle_name = str(
            vehicle_name or os.environ.get("AEGIS_AIRSIM_VEHICLE") or "Drone1"
        )
        self._rtf = float(real_time_factor)
        self._dry_run = dry_run
        self._snapshot_dir = Path(snapshot_dir or _SNAPSHOT_DIR)
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

        self._json_path = Path(visual_json_path or _VISUAL_JSON)
        self._config: dict[str, Any] = {}
        self._actors: dict[str, _Actor] = {}
        self._state = _VisualState()
        self._module: Any | None = None
        self._client: Any | None = None
        self._available_assets: list[str] | None = None
        self._animation_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._client_lock = threading.Lock()

        self._load_config()
        self._build_actors()

    # ------------------------------------------------------------------
    # Public API — connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to AirSim. Returns True on success."""
        if self._dry_run:
            logger.info("[VisualCtrl] dry_run=True — skipping AirSim connection")
            return False
        module = _load_airsim_module()
        if module is None:
            logger.warning("[VisualCtrl] AirSim Python client not found — visual overlays disabled")
            return False
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            reachable = sock.connect_ex((self._host, self._port)) == 0
        except OSError:
            reachable = False
        finally:
            sock.close()

        if not reachable:
            logger.warning(
                "[VisualCtrl] AirSim not reachable at %s:%d — start the simulator first",
                self._host, self._port,
            )
            return False
        try:
            client = module.MultirotorClient(ip=self._host, port=self._port, timeout_value=5.0)
        except TypeError:
            client = module.MultirotorClient(ip=self._host, port=self._port)
        try:
            client.confirmConnection()
        except Exception as exc:
            logger.warning("[VisualCtrl] AirSim confirmConnection failed: %s", exc)
            return False
        self._module = module
        self._client = client
        logger.info("[VisualCtrl] Connected to AirSim at %s:%d", self._host, self._port)
        self.probe_real_actor_mode()
        return True

    # ------------------------------------------------------------------
    # Public API — Phase XI static / animation
    # ------------------------------------------------------------------

    def setup_static_scene(self) -> dict[str, Any]:
        """
        Draw all static visual elements: zones, camera markers, crime
        marker outlines, drone route, actor starting positions
        (humanoid/vehicle proxies, plus any spawned mesh assets if
        available).
        """
        if not self._client and not self.connect():
            return self._dry_run_static_report()

        results: dict[str, Any] = {
            "zones": 0, "camera_markers": 0, "actors": 0,
            "drone_route": False, "crime_markers": 0,
            "spawned_meshes": 0,
            "real_actor_mode": self._state.real_actor_mode,
        }

        try:
            self._draw_zones(results)
            self._draw_camera_markers(results)
            self._draw_actor_start_positions(results)
            self._draw_drone_route_path(results)
            self._draw_crime_marker_outlines(results)
            self._try_spawn_actor_meshes(results)
            self._state.static_drawn = True
            results["real_actor_mode"] = self._state.real_actor_mode
            logger.info("[VisualCtrl] Static scene rendered: %s", results)
        except Exception as exc:
            logger.error("[VisualCtrl] setup_static_scene error: %s", exc)
            results["error"] = str(exc)

        return results

    def run_animation(self, duration: float = 65.0) -> None:
        """Blocking animation loop. Use start_animation_thread() for non-blocking."""
        if not self._client and not self.connect():
            logger.warning("[VisualCtrl] run_animation: no AirSim connection")
            return

        self._state.running = True
        self._state.elapsed = 0.0
        self._stop_event.clear()
        tick = 0.5 / max(self._rtf, 0.1)
        logger.info("[VisualCtrl] Animation started (duration=%.1fs, rtf=%.2f)", duration, self._rtf)

        start_wall = time.monotonic()
        while not self._stop_event.is_set():
            wall_elapsed = time.monotonic() - start_wall
            self._state.elapsed = wall_elapsed * self._rtf
            if self._state.elapsed >= duration:
                break

            t = self._state.elapsed
            try:
                self._update_actor_positions(t)
                self._update_crime_markers(t)
                self._update_drone_position(t)
            except Exception as exc:
                logger.debug("[VisualCtrl] animation tick error: %s", exc)

            time.sleep(tick)

        self._state.running = False
        logger.info("[VisualCtrl] Animation complete at t=%.1fs", self._state.elapsed)

    def start_animation_thread(self, duration: float = 65.0) -> None:
        if self._animation_thread and self._animation_thread.is_alive():
            logger.info("[VisualCtrl] Animation already running")
            return
        self._stop_event.clear()
        self._animation_thread = threading.Thread(
            target=self.run_animation,
            args=(duration,),
            daemon=True,
            name="aegis-visual-animation",
        )
        self._animation_thread.start()
        logger.info("[VisualCtrl] Animation thread started")

    def stop_animation(self) -> None:
        self._stop_event.set()
        if self._animation_thread:
            self._animation_thread.join(timeout=3.0)
        self._state.running = False
        logger.info("[VisualCtrl] Animation stopped")

    def flush_markers(self) -> None:
        """Clear debug markers and destroy any spawned meshes."""
        if self._client:
            try:
                self._client.simFlushPersistentMarkers()
                logger.info("[VisualCtrl] Persistent markers flushed")
            except Exception as exc:
                logger.warning("[VisualCtrl] flush_markers error: %s", exc)
            self._destroy_spawned_meshes()
        self._state.static_drawn = False
        self._state.crime_markers_active.clear()

    # ------------------------------------------------------------------
    # Public API — Phase XII sync + snapshot
    # ------------------------------------------------------------------

    def sync_to_offset(self, t_offset_seconds: float) -> dict[str, Any]:
        """
        Push the visual state forward to scenario time t. Updates actor
        positions, crime markers, and drone position to match offset
        without running a continuous animation loop.
        """
        if not self._client and not self.connect():
            return {
                "status": "disconnected",
                "t_offset_seconds": float(t_offset_seconds),
                "reason": "AirSim not reachable",
            }
        t = max(0.0, float(t_offset_seconds))
        try:
            if not self._state.static_drawn:
                self.setup_static_scene()
            self._state.elapsed = t
            self._update_actor_positions(t)
            self._update_crime_markers(t)
            self._update_drone_position(t)
            self._state.last_sync_offset_seconds = t
            logger.info("[VisualCtrl] Synced visuals to t=%.1fs", t)
            return {
                "status": "ok",
                "t_offset_seconds": t,
                "real_actor_mode": self._state.real_actor_mode,
                "crime_markers_active": list(self._state.crime_markers_active),
            }
        except Exception as exc:
            logger.error("[VisualCtrl] sync_to_offset error: %s", exc)
            return {"status": "error", "t_offset_seconds": t, "error": str(exc)}

    def capture_camera_snapshot(self, camera_id: str) -> dict[str, Any]:
        """
        Capture a real PNG snapshot from AirSim for the given camera.

        Strategy:
          * If the camera has an entry in the visual config, teleport the
            drone briefly to that camera's pose (downward gimbal) and use
            simGetImages to grab a Scene PNG.
          * If the camera is "DRONE-ALPHA" or "Drone1", use the drone's
            own front_center capture.
          * Result is saved to runtime_state/visual_snapshots/{camera_id}.png
            and returned as a status dict.
        """
        snapshot_path = self._snapshot_dir / f"{camera_id}.png"
        if not self._client and not self.connect():
            return {
                "status": "disconnected",
                "camera_id": camera_id,
                "reason": "AirSim not reachable",
                "snapshot_path": None,
            }

        try:
            png_bytes = self._capture_png_bytes(camera_id)
            if not png_bytes:
                return {
                    "status": "no_frame",
                    "camera_id": camera_id,
                    "reason": "AirSim returned empty image payload",
                    "snapshot_path": None,
                }
            snapshot_path.write_bytes(png_bytes)
            iso = _now_iso()
            self._state.last_snapshot_at[camera_id] = iso
            logger.info(
                "[VisualCtrl] Snapshot saved: %s (%d bytes)",
                snapshot_path, len(png_bytes),
            )
            return {
                "status": "ok",
                "camera_id": camera_id,
                "snapshot_path": str(snapshot_path),
                "bytes": len(png_bytes),
                "captured_at": iso,
            }
        except Exception as exc:
            logger.warning("[VisualCtrl] capture_camera_snapshot(%s) error: %s", camera_id, exc)
            return {
                "status": "error",
                "camera_id": camera_id,
                "error": str(exc),
                "snapshot_path": None,
            }

    def capture_all_snapshots(self) -> dict[str, Any]:
        """Capture snapshots for every camera marker defined in the config."""
        if not self._client and not self.connect():
            return {
                "status": "disconnected",
                "captured": [],
                "reason": "AirSim not reachable",
            }
        captured: list[dict[str, Any]] = []
        for cam in self._config.get("camera_markers", []):
            cam_id = cam["camera_id"]
            captured.append(self.capture_camera_snapshot(cam_id))
        return {
            "status": "ok",
            "captured": captured,
            "snapshot_dir": str(self._snapshot_dir),
        }

    def probe_real_actor_mode(self) -> str:
        """
        Inspect available assets and decide which real_actor_mode the
        controller can deliver:

            * real_mesh     — character assets baked into the binary
            * spawned_mesh  — non-human spawnable meshes (vehicles, props)
            * proxy_overlay — only debug markers are possible
            * unavailable   — no AirSim connection at all

        The decision is cached on self._state.real_actor_mode and reused
        until probe_real_actor_mode() is called again.
        """
        if not self._client:
            self._state.real_actor_mode = "unavailable"
            return self._state.real_actor_mode

        assets = self._list_assets_safe()
        self._available_assets = assets

        has_human = any(
            any(hint.lower() in asset.lower() for hint in _HUMAN_MESH_HINTS)
            for asset in assets
        )
        has_vehicle = any(
            any(hint.lower() in asset.lower() for hint in _VEHICLE_MESH_HINTS)
            for asset in assets
        )
        has_prop = any(
            any(hint.lower() in asset.lower() for hint in _PROP_MESH_HINTS)
            for asset in assets
        )

        if has_human:
            mode = "real_mesh"
        elif has_vehicle or has_prop:
            mode = "spawned_mesh"
        elif assets:
            mode = "spawned_mesh"  # assets exist but no character / vehicle / prop hints matched
        else:
            mode = "proxy_overlay"

        self._state.real_actor_mode = mode
        logger.info(
            "[VisualCtrl] real_actor_mode=%s (%d assets, human=%s vehicle=%s prop=%s)",
            mode, len(assets), has_human, has_vehicle, has_prop,
        )
        return mode

    def list_available_assets(self, refresh: bool = False) -> list[str]:
        if self._available_assets is None or refresh:
            self._available_assets = self._list_assets_safe()
        return list(self._available_assets)

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self._client is not None,
            "dry_run": self._dry_run,
            "static_drawn": self._state.static_drawn,
            "animation_running": self._state.running,
            "elapsed_seconds": round(self._state.elapsed, 1),
            "actors": list(self._actors.keys()),
            "airsim_host": self._host,
            "airsim_port": self._port,
            "visual_json": str(self._json_path),
            "json_loaded": bool(self._config),
            "real_actor_mode": self._state.real_actor_mode,
            "spawned_assets": dict(self._state.spawned_assets),
            "last_snapshot_at": dict(self._state.last_snapshot_at),
            "last_sync_offset_seconds": self._state.last_sync_offset_seconds,
            "snapshot_dir": str(self._snapshot_dir),
            "available_asset_count": len(self._available_assets or []),
        }

    # ------------------------------------------------------------------
    # Internal — config / actor building
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        if not self._json_path.exists():
            logger.warning("[VisualCtrl] visual JSON not found: %s", self._json_path)
            return
        try:
            self._config = json.loads(self._json_path.read_text(encoding="utf-8"))
            logger.info("[VisualCtrl] Loaded visual config: %s", self._json_path)
        except Exception as exc:
            logger.error("[VisualCtrl] Failed to load visual JSON: %s", exc)

    def _build_actors(self) -> None:
        for raw in self._config.get("actors", []):
            actor_id = raw["actor_id"]
            start = raw.get("start_pose", {})
            pose = _Vec3(
                x=float(start.get("x", 0)),
                y=float(start.get("y", 0)),
                z=float(start.get("z", 0)),
            )
            group: list[_Vec3] = [
                _Vec3(
                    x=float(m["pose"]["x"]),
                    y=float(m["pose"]["y"]),
                    z=float(m["pose"].get("z", 1.8)),
                )
                for m in raw.get("group_members", [])
            ]
            self._actors[actor_id] = _Actor(
                actor_id=actor_id,
                label=raw.get("proxy_label", actor_id),
                color=raw.get("proxy_color_rgba", [1.0, 1.0, 1.0, 1.0]),
                size=float(raw.get("proxy_size", 15.0)),
                role=str(raw.get("role", "")),
                current_pose=pose,
                waypoints=raw.get("waypoints", []),
                group_members=group,
            )
        logger.debug("[VisualCtrl] Built %d actors", len(self._actors))

    # ------------------------------------------------------------------
    # Internal — drawing helpers (Phase XI primitives)
    # ------------------------------------------------------------------

    def _v3r(self, x: float, y: float, z_alt: float) -> Any:
        return self._module.Vector3r(x, y, -z_alt)

    def _quat(self, pitch: float, roll: float, yaw: float) -> Any:
        """Build an AirSim quaternion even when the Cosys client lacks to_quaternion."""
        converter = getattr(self._module, "to_quaternion", None)
        if callable(converter):
            return converter(pitch, roll, yaw)

        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        return self._module.Quaternionr(
            x_val=cy * sr * cp - sy * cr * sp,
            y_val=cy * cr * sp + sy * sr * cp,
            z_val=sy * cr * cp - cy * sr * sp,
            w_val=cy * cr * cp + sy * sr * sp,
        )

    def _draw_zones(self, results: dict[str, Any]) -> None:
        dur = float(self._config.get("visuals", {}).get("marker_duration_seconds", 3600.0))
        thickness = float(self._config.get("visuals", {}).get("zone_thickness", 2.5))

        for zone in self._config.get("zones", []):
            cx = float(zone["center"]["x"])
            cy = float(zone["center"]["y"])
            cz = float(zone["center"].get("z", 0.5))
            dx = float(zone["extents"]["dx"]) / 2.0
            dy = float(zone["extents"]["dy"]) / 2.0
            rgba = zone["color_rgba"]
            label = zone["label"]
            lh = float(zone.get("label_height", 8.0))

            corners = [
                self._v3r(cx - dx, cy - dy, cz),
                self._v3r(cx + dx, cy - dy, cz),
                self._v3r(cx + dx, cy + dy, cz),
                self._v3r(cx - dx, cy + dy, cz),
                self._v3r(cx - dx, cy - dy, cz),
            ]
            self._plot_line_strip(corners, rgba, thickness, dur)
            self._plot_strings([label], [self._v3r(cx, cy, lh)], rgba, dur)
            results["zones"] += 1

    def _draw_camera_markers(self, results: dict[str, Any]) -> None:
        dur = float(self._config.get("visuals", {}).get("marker_duration_seconds", 3600.0))
        marker_size = 14.0
        lh_offset = 3.5
        label_color = [0.0, 1.0, 0.2, 1.0]

        for cam in self._config.get("camera_markers", []):
            cam_id = cam["camera_id"]
            cx = float(cam["pose"]["x"])
            cy = float(cam["pose"]["y"])
            cz = float(cam["pose"].get("z", 4.5))
            rgba = cam.get("color_rgba", [0.0, 1.0, 0.2, 1.0])

            diamond = [
                self._v3r(cx,       cy - 1.5, cz),
                self._v3r(cx + 1.5, cy,       cz),
                self._v3r(cx,       cy + 1.5, cz),
                self._v3r(cx - 1.5, cy,       cz),
                self._v3r(cx,       cy - 1.5, cz),
            ]
            self._plot_line_strip(diamond, rgba, 2.5, dur)
            self._plot_points([self._v3r(cx, cy, cz)], rgba, marker_size, dur)
            self._plot_strings([cam_id], [self._v3r(cx, cy, cz + lh_offset)], label_color, dur)
            results["camera_markers"] += 1

    def _draw_actor_start_positions(self, results: dict[str, Any]) -> None:
        dur = float(self._config.get("visuals", {}).get("marker_duration_seconds", 3600.0))
        for actor in self._actors.values():
            if actor.group_members:
                # Civilians: each member drawn as humanoid stack + group label.
                for member in actor.group_members:
                    self._draw_humanoid(member, actor.color, actor.size, dur)
                cx = sum(m.x for m in actor.group_members) / len(actor.group_members)
                cy = sum(m.y for m in actor.group_members) / len(actor.group_members)
                cz = actor.group_members[0].z + 3.5
                self._plot_strings([actor.label], [self._v3r(cx, cy, cz)], actor.color, dur)
            elif self._is_vehicle(actor):
                self._draw_vehicle(actor.current_pose, actor.color, actor.size, dur)
                p = actor.current_pose
                self._plot_strings(
                    [actor.label],
                    [self._v3r(p.x, p.y, p.z + 4.0)],
                    actor.color, dur,
                )
            else:
                self._draw_humanoid(actor.current_pose, actor.color, actor.size, dur)
                p = actor.current_pose
                self._plot_strings(
                    [actor.label],
                    [self._v3r(p.x, p.y, p.z + 3.5)],
                    actor.color, dur,
                )
            results["actors"] += 1

    def _draw_drone_route_path(self, results: dict[str, Any]) -> None:
        route_cfg = self._config.get("drone_route", {})
        if not route_cfg:
            return
        dur = float(self._config.get("visuals", {}).get("marker_duration_seconds", 3600.0))
        rgba = route_cfg.get("path_color_rgba", [0.0, 1.0, 0.9, 1.0])
        thickness = 5.0
        wpt_size = 12.0

        pts = []
        for wp in route_cfg.get("waypoints", []):
            x = float(wp["pose"]["x"])
            y = float(wp["pose"]["y"])
            z = float(wp["pose"]["z"])
            pts.append(self._v3r(x, y, z))

        if len(pts) >= 2:
            self._plot_line_strip(pts, rgba, thickness, dur)
        if pts:
            self._plot_points(pts, rgba, wpt_size, dur)
            first = route_cfg["waypoints"][0]
            last = route_cfg["waypoints"][-1]
            self._plot_strings(
                ["DRONE-ALPHA DISPATCH"],
                [self._v3r(first["pose"]["x"], first["pose"]["y"], first["pose"]["z"] + 3)],
                rgba, dur,
            )
            self._plot_strings(
                ["DRONE-ALPHA FINAL"],
                [self._v3r(last["pose"]["x"], last["pose"]["y"], last["pose"]["z"] + 3)],
                rgba, dur,
            )
        results["drone_route"] = True

    def _draw_crime_marker_outlines(self, results: dict[str, Any]) -> None:
        """Draw the outline rings for crime markers so the locations are
        visible before their trigger time fires."""
        dur = float(self._config.get("visuals", {}).get("marker_duration_seconds", 3600.0))
        for cm in self._config.get("crime_markers", []):
            cx = float(cm["pose"]["x"])
            cy = float(cm["pose"]["y"])
            cz = float(cm["pose"].get("z", 0.5))
            rgba = cm["color_rgba"]
            # Outline ring made of 16 points
            ring: list[Any] = []
            r = float(cm.get("outline_radius", 4.5))
            for i in range(17):
                a = (i / 16.0) * 2 * math.pi
                ring.append(self._v3r(cx + r * math.cos(a), cy + r * math.sin(a), cz))
            self._plot_line_strip(ring, rgba, 1.5, dur)
            results["crime_markers"] += 1

    # ------------------------------------------------------------------
    # Internal — humanoid / vehicle proxy primitives (Phase XII)
    # ------------------------------------------------------------------

    def _draw_humanoid(
        self, pose: _Vec3, color: list[float], size: float, duration: float
    ) -> None:
        """Draw a humanoid silhouette using a body sphere + head sphere.

        The stack is visible from every camera angle and reads much more
        clearly as a person than a single flat dot.
        """
        body = self._v3r(pose.x, pose.y, pose.z + 0.9)
        head = self._v3r(pose.x, pose.y, pose.z + 1.7)
        feet = self._v3r(pose.x, pose.y, pose.z + 0.1)
        head_color = [
            min(1.0, color[0] * 0.85 + 0.15),
            min(1.0, color[1] * 0.85 + 0.15),
            min(1.0, color[2] * 0.85 + 0.15),
            color[3] if len(color) > 3 else 1.0,
        ]
        self._plot_points([body], color, max(size, 14.0), duration)
        self._plot_points([head], head_color, max(size * 0.55, 8.0), duration)
        self._plot_points([feet], color, max(size * 0.45, 6.0), duration)

    def _draw_vehicle(
        self, pose: _Vec3, color: list[float], size: float, duration: float
    ) -> None:
        """Draw a vehicle silhouette using 4 corner points + roof point + outline."""
        half_l = 2.4
        half_w = 1.0
        z = pose.z + 0.6
        roof = self._v3r(pose.x, pose.y, pose.z + 1.4)
        corners = [
            self._v3r(pose.x + half_l, pose.y + half_w, z),
            self._v3r(pose.x + half_l, pose.y - half_w, z),
            self._v3r(pose.x - half_l, pose.y - half_w, z),
            self._v3r(pose.x - half_l, pose.y + half_w, z),
            self._v3r(pose.x + half_l, pose.y + half_w, z),
        ]
        self._plot_line_strip(corners, color, 3.0, duration)
        self._plot_points(corners[:-1], color, max(size * 0.5, 10.0), duration)
        self._plot_points([roof], color, max(size * 0.7, 12.0), duration)

    def _is_vehicle(self, actor: _Actor) -> bool:
        return (actor.role or "").lower() == "vehicle"

    # ------------------------------------------------------------------
    # Internal — asset spawn / pose (Phase XII real_mesh path)
    # ------------------------------------------------------------------

    def _list_assets_safe(self) -> list[str]:
        if not self._client:
            return []
        try:
            assets = self._client.simListAssets()
            if isinstance(assets, list):
                return [str(a) for a in assets]
            return []
        except Exception as exc:
            logger.info("[VisualCtrl] simListAssets unavailable: %s", exc)
            return []

    def _pick_asset(self, hints: tuple[str, ...]) -> str | None:
        for asset in self._available_assets or []:
            for hint in hints:
                if hint.lower() in asset.lower():
                    return asset
        return None

    def _try_spawn_actor_meshes(self, results: dict[str, Any]) -> None:
        """
        If the binary exposes mesh assets, spawn real meshes for actors.
        Only attempted when probe_real_actor_mode() returned spawned_mesh
        or real_mesh — otherwise the proxy overlay above is the only
        visual.
        """
        if self._state.real_actor_mode not in ("real_mesh", "spawned_mesh"):
            return
        if self._available_assets is None:
            self._available_assets = self._list_assets_safe()
        if not self._available_assets:
            return

        spawned = 0
        for actor in self._actors.values():
            hints = (
                _HUMAN_MESH_HINTS
                if not self._is_vehicle(actor)
                else _VEHICLE_MESH_HINTS
            )
            asset = self._pick_asset(hints)
            if asset is None:
                continue
            object_name = f"AegisActor_{actor.actor_id.replace('-', '_')}"
            if actor.group_members:
                # Spawn one mesh per civilian where possible
                for i, member in enumerate(actor.group_members):
                    name_i = f"{object_name}_M{i}"
                    if self._spawn_at(name_i, asset, member):
                        actor.spawned_object_name = actor.spawned_object_name or name_i
                        self._state.spawned_assets[name_i] = asset
                        spawned += 1
            else:
                if self._spawn_at(object_name, asset, actor.current_pose):
                    actor.spawned_object_name = object_name
                    self._state.spawned_assets[object_name] = asset
                    spawned += 1

        results["spawned_meshes"] = spawned
        if spawned > 0:
            logger.info("[VisualCtrl] Spawned %d real mesh proxies", spawned)

    def _spawn_at(self, object_name: str, asset_name: str, pose: _Vec3) -> bool:
        try:
            airsim_pose = self._module.Pose(
                self._v3r(pose.x, pose.y, pose.z),
                self._quat(0.0, 0.0, 0.0),
            )
            scale = self._module.Vector3r(1.0, 1.0, 1.0)
            self._client.simSpawnObject(
                object_name, asset_name, airsim_pose, scale, False, False
            )
            return True
        except Exception as exc:
            logger.debug("[VisualCtrl] simSpawnObject(%s,%s) failed: %s", object_name, asset_name, exc)
            return False

    def _set_object_pose(self, object_name: str, pose: _Vec3) -> None:
        try:
            airsim_pose = self._module.Pose(
                self._v3r(pose.x, pose.y, pose.z),
                self._quat(0.0, 0.0, 0.0),
            )
            self._client.simSetObjectPose(object_name, airsim_pose, True)
        except Exception as exc:
            logger.debug("[VisualCtrl] simSetObjectPose(%s) failed: %s", object_name, exc)

    def _destroy_spawned_meshes(self) -> None:
        if not self._client or not self._state.spawned_assets:
            return
        for name in list(self._state.spawned_assets):
            try:
                self._client.simDestroyObject(name)
            except Exception:
                pass
        self._state.spawned_assets.clear()

    # ------------------------------------------------------------------
    # Internal — animation tick helpers
    # ------------------------------------------------------------------

    def _update_actor_positions(self, t: float) -> None:
        dur = 2.0
        for actor in self._actors.values():
            if not actor.active:
                continue
            if actor.group_members:
                self._animate_group(actor, t, dur)
            elif actor.waypoints:
                pose = self._interpolate_waypoints(actor.waypoints, t)
                if pose:
                    actor.current_pose = pose
                    if self._is_vehicle(actor):
                        self._draw_vehicle(pose, actor.color, actor.size, dur)
                    else:
                        self._draw_humanoid(pose, actor.color, actor.size, dur)
                    self._plot_strings(
                        [actor.label],
                        [self._v3r(pose.x, pose.y, pose.z + 3.5)],
                        actor.color, dur,
                    )
                    if actor.spawned_object_name:
                        self._set_object_pose(actor.spawned_object_name, pose)

    def _animate_group(self, actor: _Actor, t: float, dur: float) -> None:
        scatter_t = 9999.0
        scatter_r = 18.0
        scatter_dir = [1.0, -1.0]
        for raw in self._config.get("actors", []):
            if raw["actor_id"] == actor.actor_id:
                scatter_t = float(raw.get("scatter_trigger_offset_seconds", 9999.0))
                scatter_r = float(raw.get("scatter_radius", 18.0))
                scatter_dir = raw.get("scatter_direction", [1.0, -1.0])
                break

        for i, member in enumerate(actor.group_members):
            if t >= scatter_t:
                angle = (i / max(len(actor.group_members), 1)) * 2 * math.pi
                progress = min((t - scatter_t) / 10.0, 1.0)
                sx = member.x + scatter_dir[0] * scatter_r * progress * math.cos(angle)
                sy = member.y + scatter_dir[1] * scatter_r * progress * math.sin(angle)
                pose = _Vec3(sx, sy, member.z)
                self._draw_humanoid(pose, actor.color, actor.size, dur)
            else:
                self._draw_humanoid(member, actor.color, actor.size, dur)

    def _update_crime_markers(self, t: float) -> None:
        dur = 2.0
        for cm in self._config.get("crime_markers", []):
            trigger = float(cm.get("trigger_offset_seconds", 9999.0))
            if t < trigger:
                continue
            mid = cm["marker_id"]
            cx = float(cm["pose"]["x"])
            cy = float(cm["pose"]["y"])
            cz = float(cm["pose"].get("z", 0.5))
            rgba = cm["color_rgba"]
            size = float(cm.get("size", 25.0))
            label = cm.get("label", mid)
            tick_int = int(t * 2) % 2
            effective_size = size if tick_int == 0 else size * 0.6
            self._plot_points([self._v3r(cx, cy, cz)], rgba, effective_size, dur)
            self._plot_strings([label], [self._v3r(cx, cy, cz + 4.0)], rgba, dur)
            if mid not in self._state.crime_markers_active:
                logger.info("[VisualCtrl] Crime marker activated: %s at t=%.1f", mid, t)
                self._state.crime_markers_active.add(mid)

    def _update_drone_position(self, t: float) -> None:
        route_cfg = self._config.get("drone_route", {})
        dispatch_t = float(route_cfg.get("dispatch_trigger_offset_seconds", 25.0))
        if t < dispatch_t:
            return
        wpts = route_cfg.get("waypoints", [])
        if not wpts:
            return
        pose = self._interpolate_waypoints(wpts, t)
        if pose is None:
            last = wpts[-1]
            pose = _Vec3(
                x=float(last["pose"]["x"]),
                y=float(last["pose"]["y"]),
                z=float(last["pose"]["z"]),
            )
        rgba = route_cfg.get("path_color_rgba", [0.0, 1.0, 0.9, 1.0])
        dur = 2.0
        # Cross-shaped drone marker so it stands apart from actor dots
        self._plot_points([self._v3r(pose.x, pose.y, pose.z)], rgba, 22.0, dur)
        cross = [
            self._v3r(pose.x - 2, pose.y, pose.z),
            self._v3r(pose.x + 2, pose.y, pose.z),
            self._v3r(pose.x, pose.y, pose.z),
            self._v3r(pose.x, pose.y - 2, pose.z),
            self._v3r(pose.x, pose.y + 2, pose.z),
        ]
        self._plot_line_strip(cross, rgba, 2.5, dur)
        self._plot_strings(["DRONE-ALPHA"], [self._v3r(pose.x, pose.y, pose.z + 5.0)], rgba, dur)
        try:
            self._client.simSetVehiclePose(
                self._module.Pose(
                    self._v3r(pose.x, pose.y, pose.z),
                    self._quat(0, 0, 0),
                ),
                ignore_collision=True,
                vehicle_name=self._vehicle_name,
            )
        except Exception:
            pass

    @staticmethod
    def _interpolate_waypoints(
        waypoints: list[dict[str, Any]], t: float
    ) -> _Vec3 | None:
        if not waypoints:
            return None
        sorted_wps = sorted(waypoints, key=lambda w: float(w.get("offset_seconds", 0)))
        first = sorted_wps[0]
        if t <= float(first.get("offset_seconds", 0)):
            p = first["pose"]
            return _Vec3(float(p["x"]), float(p["y"]), float(p.get("z", 1.8)))
        last = sorted_wps[-1]
        if t >= float(last.get("offset_seconds", 0)):
            return None
        for i in range(len(sorted_wps) - 1):
            wp0 = sorted_wps[i]
            wp1 = sorted_wps[i + 1]
            t0 = float(wp0.get("offset_seconds", 0))
            t1 = float(wp1.get("offset_seconds", 0))
            if t0 <= t <= t1:
                alpha = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                p0 = wp0["pose"]
                p1 = wp1["pose"]
                return _Vec3(
                    x=float(p0["x"]) + alpha * (float(p1["x"]) - float(p0["x"])),
                    y=float(p0["y"]) + alpha * (float(p1["y"]) - float(p0["y"])),
                    z=float(p0.get("z", 1.8)) + alpha * (float(p1.get("z", 1.8)) - float(p0.get("z", 1.8))),
                )
        return None

    # ------------------------------------------------------------------
    # Internal — snapshot capture (Phase XII)
    # ------------------------------------------------------------------

    def _capture_png_bytes(self, camera_id: str) -> bytes | None:
        """Capture a PNG snapshot for camera_id by teleporting the drone to
        the camera's viewpoint (downward gimbal) and using simGetImages.

        Returns None if AirSim is connected but returns no image."""
        cam_cfg = self._find_camera_marker(camera_id)
        if cam_cfg is None and camera_id not in {"DRONE-ALPHA", "Drone1"}:
            logger.info("[VisualCtrl] camera_id %s not in visual config", camera_id)
            return None
        with self._client_lock:
            if cam_cfg is not None:
                cx = float(cam_cfg["pose"]["x"])
                cy = float(cam_cfg["pose"]["y"])
                cz = float(cam_cfg["pose"].get("z", 8.0))
                # Aim camera downward at 65 degrees so the ground is visible
                pitch = math.radians(-65.0)
                try:
                    self._client.simSetVehiclePose(
                        self._module.Pose(
                            self._v3r(cx, cy, cz),
                            self._quat(pitch, 0, 0),
                        ),
                        ignore_collision=True,
                        vehicle_name=self._vehicle_name,
                    )
                except Exception as exc:
                    logger.debug("[VisualCtrl] vehicle pose for camera %s failed: %s", camera_id, exc)
            return self._fetch_scene_png()

    def _find_camera_marker(self, camera_id: str) -> dict[str, Any] | None:
        for cam in self._config.get("camera_markers", []):
            if cam.get("camera_id") == camera_id:
                return cam
        return None

    def _fetch_scene_png(self) -> bytes | None:
        """Use simGetImages to retrieve a Scene PNG from the drone's front_center camera.

        Falls back to direct RPC call (3-arg) when the Python stub raises
        the swapped-args error we saw in Phase 56.
        """
        try:
            request = self._module.ImageRequest(
                "front_center",
                self._module.ImageType.Scene,
                False,
                True,
            )
        except Exception as exc:
            logger.debug("[VisualCtrl] ImageRequest construction failed: %s", exc)
            return None

        # Try the stub first
        try:
            responses = self._client.simGetImages([request])
        except Exception as exc:
            logger.debug("[VisualCtrl] simGetImages stub failed: %s; trying direct RPC", exc)
            responses = self._direct_rpc_image_request(request)

        if not responses:
            return None
        resp = responses[0]
        data = getattr(resp, "image_data_uint8", None)
        if data is None:
            return None
        try:
            return bytes(data)
        except Exception:
            return None

    def _direct_rpc_image_request(self, request: Any) -> list[Any]:
        """Bypass the Python stub and call simGetImages with 3-arg form."""
        try:
            req_dict = {
                "camera_name": request.camera_name,
                "image_type": int(request.image_type),
                "pixels_as_float": bool(request.pixels_as_float),
                "compress": bool(request.compress),
            }
            raw = self._client.client.call(
                "simGetImages", [req_dict], "", False
            )
            if not isinstance(raw, list):
                return []
            return [self._module.ImageResponse.from_msgpack(r) for r in raw]
        except Exception as exc:
            logger.debug("[VisualCtrl] direct RPC simGetImages failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal — low-level AirSim plot wrappers (safe no-ops if no client)
    # ------------------------------------------------------------------

    def _plot_points(
        self, points: list[Any], color: list[float], size: float, duration: float
    ) -> None:
        if not self._client:
            return
        try:
            self._client.simPlotPoints(points, color, size, duration, is_persistent=False)
        except Exception as exc:
            logger.debug("[VisualCtrl] simPlotPoints error: %s", exc)

    def _plot_line_strip(
        self, points: list[Any], color: list[float], thickness: float, duration: float
    ) -> None:
        if not self._client or len(points) < 2:
            return
        try:
            self._client.simPlotLineStrip(points, color, thickness, duration, is_persistent=True)
        except Exception as exc:
            logger.debug("[VisualCtrl] simPlotLineStrip error: %s", exc)

    def _plot_strings(
        self,
        strings: list[str],
        positions: list[Any],
        color: list[float],
        duration: float,
    ) -> None:
        if not self._client or not strings or not positions:
            return
        try:
            self._client.simPlotStrings(strings, positions, 1.8, color, duration)
        except Exception as exc:
            logger.debug("[VisualCtrl] simPlotStrings error: %s", exc)

    # ------------------------------------------------------------------
    # Dry-run / status helpers
    # ------------------------------------------------------------------

    def _dry_run_static_report(self) -> dict[str, Any]:
        actors = len(self._actors)
        cameras = len(self._config.get("camera_markers", []))
        zones = len(self._config.get("zones", []))
        drone_wps = len(self._config.get("drone_route", {}).get("waypoints", []))
        return {
            "dry_run": True,
            "zones": zones,
            "camera_markers": cameras,
            "actors": actors,
            "drone_route": drone_wps > 0,
            "crime_markers": len(self._config.get("crime_markers", [])),
            "real_actor_mode": "unavailable",
            "spawned_meshes": 0,
            "note": (
                "AirSim not connected. Visual scene config loaded and validated. "
                "Start a Cosys-AirSim runtime to render visuals."
            ),
        }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_controller: AegisVisualScenarioController | None = None
_controller_lock = threading.Lock()


def get_visual_scenario_controller() -> AegisVisualScenarioController:
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = AegisVisualScenarioController()
    return _controller


def reset_visual_scenario_controller() -> None:
    """Test-only helper: drop the cached singleton."""
    global _controller
    with _controller_lock:
        _controller = None
