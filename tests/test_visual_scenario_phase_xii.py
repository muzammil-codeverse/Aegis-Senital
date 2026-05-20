"""Phase XII — Visual scenario controller and sync-service tests.

Covers:
  * Controller config loading, dry-run static report shape
  * Humanoid + vehicle proxy rendering (counted via mocked plot APIs)
  * sync_to_offset advances visual clock and triggers crime markers
  * snapshot capture writes PNG bytes to disk
  * Sync service start_for_demo / handle_step / capture_all flow
  * Per-camera status reporting and snapshot URL building
  * Real-actor-mode probe correctly classifies asset lists

All tests run without a live AirSim instance — they use an in-memory mock
client that implements just enough of the cosys-airsim surface for the
controller to exercise its code paths.
"""
from __future__ import annotations

import io
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Mock AirSim module
# ---------------------------------------------------------------------------

@dataclass
class _Vector3r:
    x_val: float = 0.0
    y_val: float = 0.0
    z_val: float = 0.0

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x_val = float(x)
        self.y_val = float(y)
        self.z_val = float(z)


@dataclass
class _Quaternionr:
    w_val: float = 1.0
    x_val: float = 0.0
    y_val: float = 0.0
    z_val: float = 0.0


@dataclass
class _Pose:
    position: _Vector3r
    orientation: _Quaternionr


class _ImageType:
    Scene = 0


@dataclass
class _ImageRequest:
    camera_name: str
    image_type: int
    pixels_as_float: bool
    compress: bool


@dataclass
class _ImageResponse:
    image_data_uint8: bytes = b""
    width: int = 32
    height: int = 32

    @classmethod
    def from_msgpack(cls, raw: dict) -> "_ImageResponse":
        return cls(image_data_uint8=raw.get("image_data_uint8", b""), width=raw.get("width", 32), height=raw.get("height", 32))


class _FakeMultirotorClient:
    def __init__(self, *args, **kwargs):
        self.plot_points_calls: list[tuple] = []
        self.plot_line_strip_calls: list[tuple] = []
        self.plot_strings_calls: list[tuple] = []
        self.flush_called = 0
        self.set_vehicle_pose_calls: list[tuple] = []
        self.spawn_calls: list[tuple] = []
        self.destroy_calls: list[str] = []
        self.list_assets_value: list[str] = []
        self.fake_image_bytes: bytes = b"\x89PNG\r\n\x1a\nFAKEPNGBYTES"
        self.connection_confirmed = 0

    # Connection / introspection
    def confirmConnection(self):
        self.connection_confirmed += 1
        return True

    def simListAssets(self):
        return list(self.list_assets_value)

    # Drawing
    def simPlotPoints(self, points, color, size, duration, is_persistent=False):
        self.plot_points_calls.append((points, color, size, duration, is_persistent))

    def simPlotLineStrip(self, points, color, thickness, duration, is_persistent=False):
        self.plot_line_strip_calls.append((points, color, thickness, duration, is_persistent))

    def simPlotStrings(self, strings, positions, scale, color, duration):
        self.plot_strings_calls.append((strings, positions, scale, color, duration))

    def simFlushPersistentMarkers(self):
        self.flush_called += 1

    # Spawn / pose
    def simSpawnObject(self, object_name, asset_name, pose, scale, physics, is_blueprint):
        self.spawn_calls.append((object_name, asset_name, pose, scale, physics, is_blueprint))
        return object_name

    def simSetObjectPose(self, object_name, pose, teleport):
        return True

    def simDestroyObject(self, object_name):
        self.destroy_calls.append(object_name)

    def simSetVehiclePose(self, pose, ignore_collision, vehicle_name):
        self.set_vehicle_pose_calls.append((pose, ignore_collision, vehicle_name))

    # Snapshot
    def simGetImages(self, requests):
        return [_ImageResponse(image_data_uint8=self.fake_image_bytes, width=32, height=32) for _ in requests]


class _FakeAirsimModule:
    Vector3r = _Vector3r
    Quaternionr = _Quaternionr
    Pose = _Pose
    ImageType = _ImageType
    ImageRequest = _ImageRequest
    ImageResponse = _ImageResponse
    MultirotorClient = _FakeMultirotorClient

    @staticmethod
    def to_quaternion(pitch, roll, yaw):
        return _Quaternionr()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_module(monkeypatch):
    """Patch the airsim module loader to return our fake module and a
    pre-built fake client. Returns a tuple (module, client_factory)."""
    import app.services.visual_scenario_controller as vsc_mod

    fake = _FakeAirsimModule()
    # The controller will call MultirotorClient(...) -> _FakeMultirotorClient
    monkeypatch.setattr(vsc_mod, "_load_airsim_module", lambda: fake)
    # Don't actually open a socket
    import socket

    class _OkSock:
        def __init__(self, *args, **kwargs):
            self._closed = False

        def settimeout(self, _):
            return None

        def connect_ex(self, *_):
            return 0

        def close(self):
            self._closed = True

    monkeypatch.setattr(socket, "socket", lambda *a, **k: _OkSock())
    return fake


@pytest.fixture
def fresh_controller(monkeypatch, tmp_path, fake_module):
    """Build a fresh controller bound to a tmp snapshot dir."""
    from app.services.visual_scenario_controller import (
        AegisVisualScenarioController,
        reset_visual_scenario_controller,
    )
    reset_visual_scenario_controller()
    ctrl = AegisVisualScenarioController(
        snapshot_dir=tmp_path / "snapshots",
    )
    yield ctrl
    reset_visual_scenario_controller()


@pytest.fixture
def fresh_sync_service(monkeypatch, fresh_controller):
    """Build a sync service backed by the fresh controller."""
    from app.services.visual_scenario_sync_service import (
        VisualScenarioSyncService,
        reset_visual_scenario_sync_service,
    )
    reset_visual_scenario_sync_service()
    svc = VisualScenarioSyncService(
        controller_factory=lambda: fresh_controller,
        snapshot_dir=fresh_controller._snapshot_dir,
    )
    yield svc
    reset_visual_scenario_sync_service()


# ---------------------------------------------------------------------------
# Controller — configuration / dry-run
# ---------------------------------------------------------------------------

def test_controller_loads_visual_config(fresh_controller):
    assert fresh_controller._json_path.exists()
    assert fresh_controller._config["scenario_id"] == "bank_robbery_visual"
    assert {a.actor_id for a in fresh_controller._actors.values()} >= {
        "SUSPECT-001", "CIVILIAN-GROUP-001", "SECURITY-GUARD-001", "ESCAPE-VEHICLE-001",
    }


def test_dry_run_setup_returns_structured_report(monkeypatch, tmp_path):
    """When AirSim is unreachable, setup_static_scene degrades gracefully."""
    from app.services.visual_scenario_controller import (
        AegisVisualScenarioController,
        reset_visual_scenario_controller,
    )
    reset_visual_scenario_controller()
    ctrl = AegisVisualScenarioController(
        snapshot_dir=tmp_path / "snapshots",
        dry_run=True,
    )
    result = ctrl.setup_static_scene()
    assert result["dry_run"] is True
    assert result["actors"] == 4
    assert result["camera_markers"] >= 8
    assert result["zones"] >= 5
    assert result["real_actor_mode"] == "unavailable"


# ---------------------------------------------------------------------------
# Controller — humanoid / vehicle proxies
# ---------------------------------------------------------------------------

def test_setup_static_scene_draws_humanoid_and_vehicle_proxies(fresh_controller, fake_module):
    assert fresh_controller.connect() is True
    result = fresh_controller.setup_static_scene()
    assert result["actors"] == 4
    client = fresh_controller._client
    # Humanoid stack draws 3 simPlotPoints per actor instance; vehicle draws
    # 5 corner points + 1 roof point; group civilians draw 5 members.
    # Each non-vehicle actor (suspect + guard) → 3 points each = 6.
    # Civilian group: 5 members × 3 points = 15.
    # Escape vehicle: 4 corners + roof = 5 (point calls) and 1 line strip.
    # Plus camera markers (8) drawing diamond + center point = 16 point calls.
    # We do not pin an exact number — instead assert > a reasonable floor.
    assert len(client.plot_points_calls) >= 20, (
        f"expected many simPlotPoints calls, got {len(client.plot_points_calls)}"
    )
    # Vehicle outline should be a line strip with 5 corner points.
    vehicle_strips = [
        call for call in client.plot_line_strip_calls
        if len(call[0]) == 5
    ]
    assert vehicle_strips, "vehicle outline line-strip not drawn"
    # Labels were drawn for every actor (4 actors + group label + camera labels)
    assert len(client.plot_strings_calls) >= 4 + 8


def test_setup_renders_zones_and_drone_route(fresh_controller, fake_module):
    fresh_controller.connect()
    result = fresh_controller.setup_static_scene()
    assert result["zones"] == 5
    assert result["camera_markers"] == 8
    assert result["drone_route"] is True


# ---------------------------------------------------------------------------
# Controller — real_actor_mode probe
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("assets", "expected"),
    [
        (["SK_Mannequin_Male", "BP_Sedan"], "real_mesh"),
        (["BP_Sedan", "TrafficCone"], "spawned_mesh"),
        (["RandomMeshFoo", "SomeProp"], "spawned_mesh"),
        ([], "proxy_overlay"),
    ],
)
def test_probe_real_actor_mode_classifies_assets(fresh_controller, fake_module, assets, expected):
    fresh_controller.connect()
    fresh_controller._client.list_assets_value = list(assets)
    assert fresh_controller.probe_real_actor_mode() == expected


def test_probe_real_actor_mode_when_disconnected(monkeypatch, tmp_path, fake_module):
    """When AirSim is unreachable, mode resolves to unavailable."""
    from app.services.visual_scenario_controller import (
        AegisVisualScenarioController,
        reset_visual_scenario_controller,
    )
    reset_visual_scenario_controller()
    ctrl = AegisVisualScenarioController(
        snapshot_dir=tmp_path / "snapshots",
        dry_run=True,
    )
    assert ctrl.probe_real_actor_mode() == "unavailable"


def test_quaternion_fallback_supports_cosys_client_without_converter(fresh_controller):
    class _ModuleWithoutConverter:
        Quaternionr = _Quaternionr

    fresh_controller._module = _ModuleWithoutConverter()

    quat = fresh_controller._quat(0.0, 0.0, 0.0)

    assert quat.w_val == pytest.approx(1.0)
    assert quat.x_val == pytest.approx(0.0)
    assert quat.y_val == pytest.approx(0.0)
    assert quat.z_val == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Controller — sync_to_offset
# ---------------------------------------------------------------------------

def test_sync_to_offset_activates_crime_markers(fresh_controller, fake_module):
    fresh_controller.connect()
    result = fresh_controller.sync_to_offset(20.0)
    assert result["status"] == "ok"
    assert "crime-bank-incident" in result["crime_markers_active"]
    assert fresh_controller._state.last_sync_offset_seconds == 20.0


def test_sync_to_offset_before_dispatch_keeps_drone_idle(fresh_controller, fake_module):
    fresh_controller.connect()
    fresh_controller.sync_to_offset(5.0)
    # Drone dispatch is at t=25; before that, no vehicle pose update should
    # occur for the drone.
    assert fresh_controller._client.set_vehicle_pose_calls == []


def test_sync_to_offset_after_dispatch_moves_drone(fresh_controller, fake_module):
    fresh_controller.connect()
    fresh_controller.sync_to_offset(30.0)
    assert fresh_controller._client.set_vehicle_pose_calls, (
        "drone should have been re-posed after dispatch"
    )


# ---------------------------------------------------------------------------
# Controller — snapshot capture
# ---------------------------------------------------------------------------

def test_capture_camera_snapshot_writes_png(fresh_controller, fake_module, tmp_path):
    fresh_controller.connect()
    result = fresh_controller.capture_camera_snapshot("CAM-BANK-01")
    assert result["status"] == "ok"
    assert Path(result["snapshot_path"]).exists()
    assert Path(result["snapshot_path"]).read_bytes().startswith(b"\x89PNG")


def test_capture_all_snapshots_writes_every_camera(fresh_controller, fake_module):
    fresh_controller.connect()
    out = fresh_controller.capture_all_snapshots()
    assert out["status"] == "ok"
    cam_ids = {r["camera_id"] for r in out["captured"] if r.get("status") == "ok"}
    assert {
        "CAM-BANK-01", "CAM-BANK-02", "CAM-BANK-03",
        "CAM-MARKET-01", "CAM-ROAD-01", "CAM-PARKING-01",
        "CAM-ALLEY-01", "CAM-GATE-01",
    } <= cam_ids


def test_capture_snapshot_when_disconnected(monkeypatch, tmp_path):
    """If AirSim is unreachable, capture returns disconnected status."""
    from app.services.visual_scenario_controller import (
        AegisVisualScenarioController,
        reset_visual_scenario_controller,
    )
    reset_visual_scenario_controller()
    ctrl = AegisVisualScenarioController(
        snapshot_dir=tmp_path / "snapshots",
        dry_run=True,
    )
    out = ctrl.capture_camera_snapshot("CAM-BANK-01")
    assert out["status"] == "disconnected"
    assert out["snapshot_path"] is None


# ---------------------------------------------------------------------------
# Sync service
# ---------------------------------------------------------------------------

def test_sync_service_start_for_demo_runs_setup(fresh_sync_service, fresh_controller):
    fresh_controller.connect()
    result = fresh_sync_service.start_for_demo(scenario_run_id="run-abc", duration=10.0)
    assert result["status"] == "ok"
    assert result["scenario_run_id"] == "run-abc"
    assert result["setup"]["actors"] == 4
    fresh_sync_service.stop_for_demo(flush_markers=False)


def test_sync_service_handle_step_drives_visual_clock(fresh_sync_service, fresh_controller):
    fresh_controller.connect()
    payload = {
        "step": 4,
        "t_offset_seconds": 20,
        "event_type": "weapon_detection",
        "observation": {"camera_id": "CAM-BANK-02"},
    }
    result = fresh_sync_service.handle_step(payload)
    assert result["status"] == "ok"
    assert result["t_offset_seconds"] == 20
    assert result["camera_id"] == "CAM-BANK-02"
    # Snapshot should have been captured for the step's camera
    snapshot_path = fresh_sync_service.snapshot_path_for("CAM-BANK-02")
    assert snapshot_path.exists()
    # Status now reports last camera
    cameras = fresh_sync_service.list_camera_status()
    bank2 = next(c for c in cameras if c["camera_id"] == "CAM-BANK-02")
    assert bank2["snapshot_url"] == "/api/visual-scenario/snapshots/CAM-BANK-02"
    assert bank2["last_status"] == "ok"


def test_sync_service_handle_step_skips_when_payload_invalid(fresh_sync_service):
    result = fresh_sync_service.handle_step(None)
    assert result["status"] == "skipped"


def test_sync_service_status_includes_real_actor_mode(fresh_sync_service, fresh_controller, fake_module):
    fresh_controller.connect()
    status = fresh_sync_service.get_status()
    assert status["connected"] is True
    assert status["real_actor_mode"] in {"real_mesh", "spawned_mesh", "proxy_overlay"}
    assert "snapshot_dir" in status


def test_sync_service_capture_all_recorded_in_camera_status(fresh_sync_service, fresh_controller):
    fresh_controller.connect()
    fresh_sync_service.capture_all_snapshots()
    cameras = fresh_sync_service.list_camera_status()
    captured_count = sum(1 for c in cameras if c["snapshot_url"])
    assert captured_count == len(cameras)


def test_sync_to_scenario_run_uses_scenario_timeline(fresh_sync_service, fresh_controller):
    fresh_controller.connect()

    class _FakeRun:
        scenario_id = "bank_robbery_demo"
        current_step = 5  # 1-indexed by the engine, so this means t_offset of step[4]
        total_steps = 12
        run_id = "run-xyz"

    result = fresh_sync_service.sync_to_scenario_run(_FakeRun())
    assert result["status"] == "ok"
    # Step index 4 of the bank_robbery_demo timeline has t_offset_seconds=20
    assert result["t_offset_seconds"] == 20.0


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

def test_get_visual_scenario_controller_returns_singleton(monkeypatch, tmp_path):
    from app.services.visual_scenario_controller import (
        get_visual_scenario_controller,
        reset_visual_scenario_controller,
    )
    reset_visual_scenario_controller()
    a = get_visual_scenario_controller()
    b = get_visual_scenario_controller()
    assert a is b
    reset_visual_scenario_controller()


def test_get_visual_scenario_sync_service_returns_singleton():
    from app.services.visual_scenario_sync_service import (
        get_visual_scenario_sync_service,
        reset_visual_scenario_sync_service,
    )
    reset_visual_scenario_sync_service()
    a = get_visual_scenario_sync_service()
    b = get_visual_scenario_sync_service()
    assert a is b
    reset_visual_scenario_sync_service()
