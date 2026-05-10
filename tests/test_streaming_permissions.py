from fastapi.testclient import TestClient

from app.models.security_models import UserAccount
from main import app


def _user(role: str) -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
    )


def test_streaming_permissions_enforced(monkeypatch):
    auth_service = __import__("app.services.auth_service", fromlist=["get_auth_service"]).get_auth_service()
    users = {"viewer": _user("viewer"), "supervisor": _user("supervisor")}
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: users.get(token))
    stream_manager = __import__("app.services.stream_session_manager", fromlist=["get_stream_session_manager"]).get_stream_session_manager()
    monkeypatch.setattr(stream_manager, "start_stream", lambda camera_id: {"camera_id": camera_id, "state": "running"})

    client = TestClient(app, raise_server_exceptions=False)
    viewer = client.post("/api/streams/cam_01/start", headers={"Authorization": "Bearer viewer"})
    supervisor = client.post("/api/streams/cam_01/start", headers={"Authorization": "Bearer supervisor"})

    assert viewer.status_code == 403
    assert supervisor.status_code == 200
