from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.security_models import UserAccount
from app.services import auth_service as auth_module
from app.services.face_enrollment_service import FaceEnrollmentService
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
        metadata={},
    )


def test_identity_raw_assets_disabled_by_default(tmp_path, monkeypatch):
    service = FaceEnrollmentService(image_dir=str(tmp_path / "images"))
    assert service.is_raw_asset_http_enabled() is False

    users = {"admin": _user("admin")}
    auth_service = auth_module.get_auth_service()
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: users.get(token))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/api/identity/enrollments/enr_test/images/img_test",
        headers={"Authorization": "Bearer admin"},
    )
    assert response.status_code == 404
