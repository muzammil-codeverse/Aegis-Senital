from app.models.drone_simulation_models import DroneCommandResponse
from app.models.security_models import UserAccount, UserStatus
import app.services.drone.drone_simulation_session_manager as drone_session_manager


class _FakeService:
    def __init__(self) -> None:
        self.drone_id = "drone_sim_01"
        self.config = {
            "stream": {"process_through_stream_processor": False},
            "investigation": {"max_observation_age_seconds": 120},
        }
        self.disconnected = False

    def disconnect(self) -> None:
        self.disconnected = True

    def takeoff(self) -> DroneCommandResponse:
        return DroneCommandResponse(command="takeoff", success=True, status="ok")

    def land(self) -> DroneCommandResponse:
        return DroneCommandResponse(command="land", success=True, status="ok")

    def hover(self) -> DroneCommandResponse:
        return DroneCommandResponse(command="hover", success=True, status="ok")

    def move_to_position(self, x: float, y: float, z: float, velocity: float) -> DroneCommandResponse:
        return DroneCommandResponse(command="move_to_position", success=True, status="ok")


class _FakeThread:
    def __init__(self, target=None, name=None, daemon=None):
        del target, name, daemon
        self._alive = False

    def start(self):
        self._alive = True

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        del timeout
        self._alive = False


def _user() -> UserAccount:
    return UserAccount(
        user_id="u-operator",
        username="operator",
        display_name="Operator",
        role="operator",
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
    )


def test_session_manager_prevents_duplicate_sessions(monkeypatch):
    fake_service = _FakeService()
    monkeypatch.setattr(drone_session_manager, "get_drone_simulation_service", lambda: fake_service)
    monkeypatch.setattr(drone_session_manager.threading, "Thread", _FakeThread)

    manager = drone_session_manager.DroneSimulationSessionManager()

    first = manager.start_session(_user())
    second = manager.start_session(_user())

    assert first.session_id == second.session_id
    assert manager.get_session_status().active is True

    stopped = manager.stop_session(_user())
    assert stopped.active is False
    assert fake_service.disconnected is True
