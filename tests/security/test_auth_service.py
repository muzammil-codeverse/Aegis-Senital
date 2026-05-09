import pytest

from app.models.security_models import UserStatus
from app.services import auth_service as auth_module
from app.services.audit_log_service import AuditLogService
from app.services.auth_service import AuthError, AuthService
from app.services.user_store import UserStore


class _AuditStub:
    def record(self, *args, **kwargs):
        return None


@pytest.fixture()
def service(tmp_path, monkeypatch):
    store = UserStore(str(tmp_path / "users.jsonl"))
    monkeypatch.setattr(auth_module, "get_user_store", lambda: store)
    monkeypatch.setattr(auth_module, "get_audit_log_service", lambda: _AuditStub())
    return AuthService()


def test_invalid_password_fails(service):
    service.create_user("analyst", "ChangeMe123", role="analyst")
    with pytest.raises(AuthError):
        service.login("analyst", "wrong-password")


def test_successful_login_returns_token(service):
    service.create_user("operator", "ChangeMe123", role="operator")
    payload = service.login("operator", "ChangeMe123")
    assert payload["access_token"]
    assert payload["token_type"] == "bearer"


def test_disabled_user_cannot_log_in(service):
    user = service.create_user("viewer", "ChangeMe123", role="viewer")
    service.update_user(user.user_id, {"status": UserStatus.DISABLED.value})
    with pytest.raises(AuthError):
        service.login("viewer", "ChangeMe123")


def test_password_change_validates_strength(service):
    user = service.create_user("admin", "ChangeMe123", role="admin")
    with pytest.raises(ValueError):
        service.change_password(user, "ChangeMe123", "weak")
