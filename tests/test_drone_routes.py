from fastapi.testclient import TestClient

import app.api.drone_routes as drone_routes
from app.models.drone_simulation_models import (
    DroneCameraFrame,
    DroneCommandResponse,
    DroneConnectionStatus,
    DroneHealthStatus,
    DroneRuntimeStatus,
    DroneSimulationSession,
    DroneTelemetry,
)
from app.models.security_models import AuditAction, UserAccount, UserStatus
from app.services import auth_service as auth_module
from main import app


def _user(role: str, camera_scopes: list[str]) -> UserAccount:
    return UserAccount(
        user_id=f"u-{role}",
        username=role,
        display_name=role,
        role=role,
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
        metadata={"camera_scopes": camera_scopes},
    )


def _telemetry() -> DroneTelemetry:
    return DroneTelemetry(
        status="connected",
        latitude=30.1575,
        longitude=71.5249,
        altitude_meters=40.0,
    )


def _frame() -> DroneCameraFrame:
    return DroneCameraFrame(
        status="connected",
        frame_available=True,
        frame_index=7,
        width=4,
        height=4,
        image_base64="ZmFrZQ==",
        telemetry=_telemetry(),
    )


class _FakeService:
    def __init__(self):
        self.drone_id = "drone_sim_01"
        self.config = {"connection": {"camera_name": "front_center", "vehicle_name": "Drone1"}}
        self.allowed_cameras = ("front_center", "downward")

    def latest_telemetry(self):
        return _telemetry()

    def latest_frame(self):
        return _frame()

    def get_health(self, *, active_session: bool = False):
        return DroneHealthStatus(
            status="healthy",
            simulator_connected=True,
            telemetry_available=True,
            frame_available=True,
            active_session=active_session,
        )

    def connect(self):
        return DroneConnectionStatus(
            status="connected",
            connected=True,
            vehicle_name="Drone1",
            camera_name="front_center",
        )

    def get_telemetry(self):
        return _telemetry()

    def get_frame(self):
        return _frame()

    def get_runtime_status(self):
        return DroneRuntimeStatus(
            selected_runtime="Blocks",
            available_runtimes=["Blocks"],
            fallback_used=True,
            connected=True,
            port_open=True,
        )


class _FakeManager:
    def get_session_status(self):
        return DroneSimulationSession(
            session_id="drn_session_test",
            status="running",
            active=True,
            operator_id="u-operator",
        )

    def get_latest_telemetry(self):
        return _telemetry()

    def get_latest_frame(self):
        return _frame()

    def start_session(self, user):
        return DroneSimulationSession(
            session_id="drn_session_test",
            status="running",
            active=True,
            operator_id=user.user_id,
        )

    def stop_session(self, user):
        del user
        return DroneSimulationSession(
            session_id="drn_session_test",
            status="stopped",
            active=False,
        )

    def get_flight_path(self):
        return []

    def takeoff(self):
        return DroneCommandResponse(command="takeoff", success=False, status="denied", detail="runtime unavailable")


def test_drone_status_and_frame_routes(monkeypatch):
    auth = auth_module.get_auth_service()
    monkeypatch.setattr(auth, "get_current_user_from_token", lambda token: _user("viewer", ["drone_sim_01"]))
    monkeypatch.setattr(drone_routes, "get_drone_simulation_service", lambda: _FakeService())
    monkeypatch.setattr(drone_routes, "get_drone_simulation_session_manager", lambda: _FakeManager())

    audited = []
    monkeypatch.setattr(
        drone_routes,
        "_audit",
        lambda request, action, **kwargs: audited.append(action.value if hasattr(action, "value") else str(action)),
    )

    client = TestClient(app, raise_server_exceptions=False)
    status = client.get("/api/drone-simulation/status", headers={"Authorization": "Bearer viewer"})
    frame = client.get("/api/drone-simulation/frame/latest", headers={"Authorization": "Bearer viewer"})

    assert status.status_code == 200
    assert status.json()["item"]["health"]["status"] == "healthy"
    assert frame.status_code == 200
    assert frame.json()["item"]["frame_available"] is True
    assert AuditAction.DRONE_FRAME_ACCESSED.value in audited


def test_drone_command_denied_is_audited(monkeypatch):
    auth = auth_module.get_auth_service()
    monkeypatch.setattr(auth, "get_current_user_from_token", lambda token: _user("operator", ["drone_sim_01"]))
    monkeypatch.setattr(drone_routes, "get_drone_simulation_service", lambda: _FakeService())
    monkeypatch.setattr(drone_routes, "get_drone_simulation_session_manager", lambda: _FakeManager())

    audited = []
    monkeypatch.setattr(
        drone_routes,
        "_audit",
        lambda request, action, **kwargs: audited.append(action.value if hasattr(action, "value") else str(action)),
    )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/drone-simulation/commands/takeoff", headers={"Authorization": "Bearer operator"})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert AuditAction.DRONE_COMMAND_DENIED.value in audited
