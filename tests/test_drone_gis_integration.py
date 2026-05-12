from app.models.drone_simulation_models import DroneFlightPathPoint, DroneSimulationSession, DroneTelemetry
from app.models.gis_models import CameraGeoProfile
from app.models.security_models import UserAccount, UserStatus
from app.services import gis_service
import app.services.drone.drone_simulation_session_manager as drone_session_module
import app.services.stream_session_manager as stream_session_module


class _Repo:
    def list_camera_geo_profiles(self, user):
        del user
        return [
            CameraGeoProfile(
                camera_id="cam_fixed",
                name="Fixed Camera",
                latitude=30.1577,
                longitude=71.5250,
            )
        ]

    def get_event_markers(self, **kwargs):
        del kwargs
        return []

    def get_case_markers(self, **kwargs):
        del kwargs
        return []

    def list_geofences(self, user):
        del user
        return []


class _FakeDroneManager:
    def get_flight_path(self):
        return [
            DroneFlightPathPoint(
                latitude=30.1575,
                longitude=71.5249,
                altitude_meters=40.0,
            )
        ]

    def get_latest_telemetry(self):
        return DroneTelemetry(
            status="connected",
            latitude=30.1575,
            longitude=71.5249,
            altitude_meters=40.0,
        )

    def get_session_status(self):
        return DroneSimulationSession(session_id="sess", status="running", active=True)


class _FakeStreamManager:
    def get_stream_state(self, camera_id):
        return {"camera_id": camera_id, "state": "running"}


def _admin() -> UserAccount:
    return UserAccount(
        user_id="u-admin",
        username="admin",
        display_name="Admin",
        role="admin",
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
    )


def test_drone_marker_and_path_appear_in_gis_layers(monkeypatch):
    monkeypatch.setattr(
        gis_service,
        "_fallback_drone_profile",
        lambda user: CameraGeoProfile(
            camera_id="drone_sim_01",
            name="Simulated Drone Feed",
            latitude=30.1575,
            longitude=71.5249,
            altitude_meters=40.0,
            metadata={"source_type": "drone_simulation", "simulated": True},
        ),
    )
    monkeypatch.setattr(drone_session_module, "get_drone_simulation_session_manager", lambda: _FakeDroneManager())
    monkeypatch.setattr(stream_session_module, "get_stream_session_manager", lambda: _FakeStreamManager())

    layers = gis_service.build_map_layers(
        _Repo(),
        _admin(),
        None,
        start_time=None,
        end_time=None,
        severity=None,
        event_type=None,
        camera_id=None,
        case_id=None,
        source_type=None,
    )

    assert any(camera.camera_id == "drone_sim_01" for camera in layers.cameras)
    assert layers.drone_paths
    assert layers.drone_paths[0].source_type == "drone_simulation"
    assert layers.stream_status_by_camera["drone_sim_01"]["status"] == "running"


def test_nearby_fixed_cameras_can_be_queried_from_drone_location():
    results = gis_service.find_nearby_cameras(_Repo(), _admin(), 30.1575, 71.5249, 1000.0)

    assert results
    assert results[0].camera_id == "cam_fixed"
