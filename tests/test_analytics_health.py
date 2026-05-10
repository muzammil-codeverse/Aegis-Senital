from __future__ import annotations

from app.services.analytics_service import AnalyticsService
from app.services.runtime_health_service import RuntimeHealthService


class _HealthRepository:
    storage_backend = "jsonl"

    def __init__(self, statuses, *, enabled=True, last_error=None):
        self.enabled = enabled
        self._statuses = dict(statuses)
        self._last_error = last_error

    def probe_sources(self):
        return dict(self._statuses)

    def get_source_statuses(self):
        return dict(self._statuses)

    def get_last_error(self):
        return self._last_error


def test_analytics_health_is_degraded_in_dev_when_optional_sources_are_missing(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    service = AnalyticsService(
        repository=_HealthRepository({"events": "healthy", "open_vocab": "missing"}),
        config={"analytics": {"enabled": True, "production": {"fail_if_required_storage_missing": True}}},
    )

    health = service.get_health()

    assert health.status == "degraded"
    assert health.sources["open_vocab"] == "missing"


def test_analytics_health_fails_in_production_when_required_sources_are_missing(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    service = AnalyticsService(
        repository=_HealthRepository({"events": "healthy", "model_metrics": "missing"}, last_error="postgres missing"),
        config={"analytics": {"enabled": True, "production": {"fail_if_required_storage_missing": True}}},
    )

    health = service.get_health()

    assert health.status == "failed"
    assert health.last_error == "postgres missing"


def test_runtime_health_includes_analytics_and_readiness_fails_fast(monkeypatch):
    service = RuntimeHealthService(config={"runtime": {}, "services": {}})
    ok = {"status": "ok", "detail": None}
    monkeypatch.setattr(service, "_check_database", lambda: ok)
    monkeypatch.setattr(service, "_check_redis", lambda: ok)
    monkeypatch.setattr(service, "_check_gpu", lambda: ok)
    monkeypatch.setattr(service, "_check_identity", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_open_vocab", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_segmentation", lambda: {"status": "healthy", "detail": None})
    monkeypatch.setattr(service, "_check_storage", lambda: ok)
    monkeypatch.setattr(service, "_check_model_registry", lambda: ok)
    monkeypatch.setattr(service, "_check_event_bus", lambda: ok)
    monkeypatch.setattr(service, "_check_security", lambda: ok)
    monkeypatch.setattr(service, "_check_case_management", lambda: {"enabled": True, "status": "healthy", "storage": "jsonl", "case_count": 0, "open_case_count": 0, "last_error": None})
    monkeypatch.setattr(service, "_check_llm", lambda: {"enabled": False, "status": "disabled", "detail": None})
    monkeypatch.setattr(service, "_check_osint_enrichment", lambda: {"enabled": False, "status": "disabled", "last_error": None})
    monkeypatch.setattr(service, "_check_streaming", lambda: {"enabled": True, "status": "healthy", "missing_dependencies": [], "last_error": None})
    monkeypatch.setattr(service, "_check_analytics", lambda: {"enabled": True, "status": "failed", "storage": "postgres", "sources": {"events": "healthy"}, "last_error": "required analytics storage unavailable"})

    health = service.get_health()
    readiness = service.is_ready()

    assert health["checks"]["analytics"]["status"] == "failed"
    assert readiness["ready"] is False
    assert any("analytics:" in failure for failure in readiness["failures"])
