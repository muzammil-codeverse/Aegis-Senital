from __future__ import annotations

import pytest
from app.services.runtime_health_service import RuntimeHealthService


def test_investigation_health_returns_dict():
    svc = RuntimeHealthService()
    result = svc._check_investigation()
    assert isinstance(result, dict)


def test_investigation_health_has_required_keys():
    svc = RuntimeHealthService()
    result = svc._check_investigation()
    assert "enabled" in result
    assert "status" in result
    assert "stored_hypotheses" in result
    assert "last_error" in result


def test_investigation_health_status_is_valid():
    svc = RuntimeHealthService()
    result = svc._check_investigation()
    assert result["status"] in ("healthy", "degraded", "failed", "disabled")


def test_full_health_includes_investigation():
    svc = RuntimeHealthService()
    health = svc.get_health()
    assert "investigation" in health
    assert isinstance(health["investigation"], dict)
