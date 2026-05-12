from fastapi.testclient import TestClient

import app.api.drone_routes as drone_routes
from app.models.drone_simulation_models import DroneHealthStatus, DroneSimulationSession, DroneTelemetry
from app.models.security_models import UserAccount, UserStatus
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


class _FakeService:
    drone_id = "drone_sim_01"
    config = {"connection": {"camera_name": "front_center", "vehicle_name": "Drone1"}}

    def latest_telemetry(self):
        return DroneTelemetry(status="connected")

    def latest_frame(self):
        return None

    def get_health(self, *, active_session: bool = False):
        return DroneHealthStatus(status="healthy", simulator_connected=True, active_session=active_session)

    def connect(self):
        return self.get_health(active_session=False)

    def get_telemetry(self):
        return DroneTelemetry(status="connected")


class _FakeManager:
    def get_session_status(self):
        return DroneSimulationSession(session_id="sess", status="running", active=True)

    def get_latest_telemetry(self):
        return DroneTelemetry(status="connected")

    def get_latest_frame(self):
        return None

    def start_session(self, user):
        return DroneSimulationSession(session_id="sess", status="running", active=True, operator_id=user.user_id)


def test_drone_routes_require_scope_and_permissions(monkeypatch):
    users = {
        "viewer": _user("viewer", ["drone_sim_01"]),
        "noscope": _user("viewer", ["cam_02"]),
        "operator": _user("operator", ["drone_sim_01"]),
    }
    auth = auth_module.get_auth_service()
    monkeypatch.setattr(auth, "get_current_user_from_token", lambda token: users.get(token))
    monkeypatch.setattr(drone_routes, "get_drone_simulation_service", lambda: _FakeService())
    monkeypatch.setattr(drone_routes, "get_drone_simulation_session_manager", lambda: _FakeManager())

    client = TestClient(app, raise_server_exceptions=False)

    allowed = client.get("/api/drone-simulation/status", headers={"Authorization": "Bearer viewer"})
    forbidden_scope = client.get("/api/drone-simulation/status", headers={"Authorization": "Bearer noscope"})
    denied_control = client.post("/api/drone-simulation/start", headers={"Authorization": "Bearer viewer"})
    allowed_control = client.post("/api/drone-simulation/start", headers={"Authorization": "Bearer operator"})

    assert allowed.status_code == 200
    assert forbidden_scope.status_code == 403
    assert denied_control.status_code == 403
    assert allowed_control.status_code == 200
