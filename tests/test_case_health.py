from app.repositories.case_repository import JsonlCaseRepository, PostgresCaseRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from backend.app.services.runtime_health_service import RuntimeHealthService


def _config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {
                "jsonl_dir": str(tmp_path / "cases"),
                "production_backend": "postgres",
                "require_postgres_in_production": True,
            },
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


def test_case_repository_health_reports_jsonl_healthy(tmp_path, monkeypatch):
    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    repo = JsonlCaseRepository(config=_config(tmp_path))
    health = repo.health()
    assert health["storage"] == "jsonl"
    assert health["status"] == "healthy"


def test_runtime_health_includes_case_management_and_readiness_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    service = CaseService(repository=JsonlCaseRepository(config=_config(tmp_path)), config=_config(tmp_path))
    monkeypatch.setattr("app.services.case_service.get_case_service", lambda: service)
    health_service = RuntimeHealthService(config={"runtime": {"require_postgres": False}, "services": {}})
    report = health_service.get_health(include_sensitive=True)
    assert "case_management" in report
    assert report["case_management"]["status"] in {"healthy", "degraded", "failed", "disabled"}


def test_production_case_storage_does_not_silently_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("AEGIS_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DB_URL", raising=False)
    repo = PostgresCaseRepository(config=_config(tmp_path))
    health = repo.health()
    assert repo.storage_backend == "postgres"
    assert repo.is_available() is False
    assert health["status"] == "failed"
