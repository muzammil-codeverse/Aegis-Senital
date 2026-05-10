from __future__ import annotations

from backend.app.services.identity_service import IdentityService


class _DummyStore:
    def list_enrollment_profiles(self, identity_id=None, limit=100):
        return []

    def get_enrollment_profile(self, enrollment_id):
        return None

    def delete_enrollment_profile(self, enrollment_id):
        return False

    def list_face_enrollments(self, identity_id):
        return []


class _DummyDB:
    pass


def test_identity_health_healthy(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.identity_service.get_identity_dependency_status",
        lambda **_: {
            "face": {"available": True},
            "reid": {"available": True},
            "status": "healthy",
            "failures": [],
            "warnings": [],
        },
    )
    service = IdentityService(store=_DummyStore(), db=_DummyDB(), enrollment_engine=object())
    health = service.get_health()
    assert health["status"] == "healthy"
    assert health["face_loaded"] is True


def test_identity_health_degraded(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.identity_service.get_identity_dependency_status",
        lambda **_: {
            "face": {"available": False},
            "reid": {"available": True},
            "status": "degraded",
            "failures": [],
            "warnings": ["identity.face missing"],
        },
    )
    service = IdentityService(store=_DummyStore(), db=_DummyDB(), enrollment_engine=object())
    health = service.get_health()
    assert health["status"] == "degraded"
    assert health["face_loaded"] is False
