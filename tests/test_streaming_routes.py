from fastapi.testclient import TestClient

from app.models.security_models import UserAccount
from main import app


def _user(role: str, metadata: dict | None = None) -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
        metadata=metadata or {},
    )


def test_streaming_health_and_stats_routes(monkeypatch):
    auth_service = __import__("app.services.auth_service", fromlist=["get_auth_service"]).get_auth_service()
    monkeypatch.setattr(
        auth_service,
        "get_current_user_from_token",
        lambda token: _user("viewer", metadata={"camera_scopes": ["cam_01"]}),
    )
    stream_manager = __import__("app.services.stream_session_manager", fromlist=["get_stream_session_manager"]).get_stream_session_manager()
    monkeypatch.setattr(stream_manager, "list_stream_states", lambda: [{"camera_id": "cam_01", "state": "running"}])
    monkeypatch.setattr(stream_manager, "get_stream_health", lambda camera_id: {"camera_id": camera_id, "status": "healthy"})
    monkeypatch.setattr(stream_manager, "get_stream_stats", lambda camera_id: {"camera_id": camera_id, "fps_decode": 10.0})

    client = TestClient(app, raise_server_exceptions=False)
    listing = client.get("/api/streams", headers={"Authorization": "Bearer viewer"})
    health = client.get("/api/streams/cam_01/health", headers={"Authorization": "Bearer viewer"})
    stats = client.get("/api/streams/cam_01/stats", headers={"Authorization": "Bearer viewer"})

    assert listing.status_code == 200
    assert health.status_code == 200
    assert stats.status_code == 200
    assert listing.json()["items"][0]["camera_id"] == "cam_01"
    assert health.json()["item"]["status"] == "healthy"
