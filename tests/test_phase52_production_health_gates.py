"""
Phase 52 — Production Health Gate Tests

Verifies that health/readiness/liveness endpoints exist, respond correctly,
and that production gates are NOT disabled.

NOTE: /api/system/* endpoints require 'system:read' permission (correct security
behavior). Tests use the standard _install_auth monkeypatch pattern from the
security test suite.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for p in (str(ROOT), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.models.security_models import UserAccount
from app.services import auth_service as auth_module


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


def _install_auth(monkeypatch):
    users = {
        "admin": _user("admin"),
        "operator": _user("operator"),
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))
    return users


def _get_client():
    from fastapi.testclient import TestClient
    from backend.main import app  # type: ignore
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# /health — public endpoint (no auth required)
# ---------------------------------------------------------------------------

class TestPublicHealthEndpoint:
    def test_health_endpoint_200(self):
        client = _get_client()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_status_field(self):
        client = _get_client()
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data

    def test_health_not_disabled(self):
        """Ensure /health is still a public endpoint."""
        client = _get_client()
        resp = client.get("/health")
        # Must not require auth
        assert resp.status_code not in (401, 403)


# ---------------------------------------------------------------------------
# /api/system/* — require system:read permission (auth enforced — correct)
# ---------------------------------------------------------------------------

class TestSystemEndpointsRequireAuth:
    def test_system_health_requires_auth(self):
        """/api/system/health must require authentication."""
        client = _get_client()
        resp = client.get("/api/system/health")
        assert resp.status_code in (401, 403)

    def test_system_readiness_requires_auth(self):
        """/api/system/readiness must require authentication."""
        client = _get_client()
        resp = client.get("/api/system/readiness")
        assert resp.status_code in (401, 403)

    def test_system_liveness_requires_auth(self):
        """/api/system/liveness must require authentication."""
        client = _get_client()
        resp = client.get("/api/system/liveness")
        assert resp.status_code in (401, 403)


class TestSystemEndpointsWithAuth:
    def test_system_health_returns_200_for_admin(self, monkeypatch):
        _install_auth(monkeypatch)
        client = _get_client()
        resp = client.get("/api/system/health", headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200

    def test_system_health_has_subsystems_for_admin(self, monkeypatch):
        _install_auth(monkeypatch)
        client = _get_client()
        resp = client.get("/api/system/health", headers={"Authorization": "Bearer admin"})
        data = resp.json()
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_system_readiness_200_or_503_for_admin(self, monkeypatch):
        _install_auth(monkeypatch)
        client = _get_client()
        resp = client.get("/api/system/readiness", headers={"Authorization": "Bearer admin"})
        assert resp.status_code in (200, 503)

    def test_system_readiness_has_ready_field_for_admin(self, monkeypatch):
        _install_auth(monkeypatch)
        client = _get_client()
        resp = client.get("/api/system/readiness", headers={"Authorization": "Bearer admin"})
        data = resp.json()
        assert "ready" in data

    def test_system_liveness_200_for_admin(self, monkeypatch):
        _install_auth(monkeypatch)
        client = _get_client()
        resp = client.get("/api/system/liveness", headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200

    def test_system_liveness_has_alive_true_for_admin(self, monkeypatch):
        _install_auth(monkeypatch)
        client = _get_client()
        resp = client.get("/api/system/liveness", headers={"Authorization": "Bearer admin"})
        data = resp.json()
        assert "alive" in data
        assert data["alive"] is True


# ---------------------------------------------------------------------------
# Production gates NOT disabled — test RuntimeHealthService directly
# ---------------------------------------------------------------------------

class TestProductionGatesNotDisabled:
    def test_db_check_fails_when_postgres_dsn_missing(self):
        """Database check must report degraded/error when POSTGRES_DSN absent."""
        from app.services.runtime_health_service import RuntimeHealthService

        svc = RuntimeHealthService()
        env_without_dsn = {k: v for k, v in os.environ.items() if k != "POSTGRES_DSN"}
        with patch.dict(os.environ, env_without_dsn, clear=True):
            result = svc._check_database()
        assert result["status"] in ("degraded", "error")

    def test_security_check_fails_when_jwt_secret_default_in_production(self):
        """Default JWT secret must be rejected in production."""
        from app.services.runtime_health_service import RuntimeHealthService

        svc = RuntimeHealthService()
        env = {
            "APP_ENV": "production",
            "AEGIS_JWT_SECRET": "change-this-in-production-use-a-long-random-string",
        }
        with patch.dict(os.environ, env, clear=True):
            result = svc._check_security()
        assert result["status"] == "error"

    def test_security_check_fails_when_jwt_secret_missing_in_production(self):
        """Missing JWT secret must be rejected in production."""
        from app.services.runtime_health_service import RuntimeHealthService

        svc = RuntimeHealthService()
        env = {"APP_ENV": "production"}
        with patch.dict(os.environ, env, clear=True):
            result = svc._check_security()
        assert result["status"] != "ok"

    def test_redis_check_fails_when_redis_url_missing(self):
        """Redis check must report degraded/error when REDIS_URL absent."""
        from app.services.runtime_health_service import RuntimeHealthService

        svc = RuntimeHealthService()
        env_without_redis = {k: v for k, v in os.environ.items() if k != "REDIS_URL"}
        with patch.dict(os.environ, env_without_redis, clear=True):
            result = svc._check_redis()
        assert result["status"] in ("degraded", "error")

    def test_readiness_returns_false_in_production_without_secrets(self):
        """Readiness must fail honestly in production with no secrets."""
        from app.services.runtime_health_service import RuntimeHealthService

        svc = RuntimeHealthService()
        env_no_secrets = {"APP_ENV": "production"}
        with patch.dict(os.environ, env_no_secrets, clear=True):
            result = svc.is_ready()
        assert result["ready"] is False

    def test_readiness_includes_failures_list(self):
        """Readiness result must include failures list for diagnostics."""
        from app.services.runtime_health_service import RuntimeHealthService

        svc = RuntimeHealthService()
        env_no_secrets = {"APP_ENV": "production"}
        with patch.dict(os.environ, env_no_secrets, clear=True):
            result = svc.is_ready()
        assert "failures" in result
        assert isinstance(result["failures"], list)

    def test_liveness_always_returns_true(self):
        """is_alive() must always return True when process is running."""
        from app.services.runtime_health_service import RuntimeHealthService

        svc = RuntimeHealthService()
        assert svc.is_alive() is True

    def test_readiness_has_ready_boolean(self):
        """is_ready() must always return a dict with boolean 'ready' field."""
        from app.services.runtime_health_service import RuntimeHealthService

        svc = RuntimeHealthService()
        result = svc.is_ready()
        assert isinstance(result, dict)
        assert "ready" in result
        assert isinstance(result["ready"], bool)


# ---------------------------------------------------------------------------
# Production gate: readiness 503 when not ready
# ---------------------------------------------------------------------------

class TestReadinessHTTP503:
    def test_readiness_returns_200_or_503_never_500(self, monkeypatch):
        """Readiness must return 200 or 503, never 500 (internal error)."""
        _install_auth(monkeypatch)
        client = _get_client()
        resp = client.get("/api/system/readiness", headers={"Authorization": "Bearer admin"})
        assert resp.status_code in (200, 503), f"Unexpected status: {resp.status_code}"

    def test_readiness_503_body_contains_ready_false(self, monkeypatch):
        """When readiness returns 503, the body must contain ready=false."""
        _install_auth(monkeypatch)
        client = _get_client()
        resp = client.get("/api/system/readiness", headers={"Authorization": "Bearer admin"})
        if resp.status_code == 503:
            data = resp.json()
            assert "ready" in data
            assert data["ready"] is False
