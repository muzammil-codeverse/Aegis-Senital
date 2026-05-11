from __future__ import annotations

import pytest

from app.repositories.case_repository import JsonlCaseRepository
from app.services.audit_log_service import AuditLogService
from app.services.runtime_health_service import RuntimeHealthService


class _BrokenAuditRepository:
    def append(self, entry, *, hash_chain_enabled=True):
        del entry, hash_chain_enabled
        raise RuntimeError("database unavailable")

    def health_check(self):
        class _Health:
            def to_dict(self):
                return {
                    "store": "audit_logs",
                    "backend": "postgres",
                    "status": "failed",
                    "last_error": "database unavailable",
                }

        return _Health()


def _case_config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


def test_production_rejects_jsonl_fallback_for_required_store(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    health = JsonlCaseRepository(config=_case_config(tmp_path)).health_check().to_dict()
    assert health["backend"] == "jsonl"
    assert health["status"] == "failed"


def test_postgres_missing_fails_production_readiness(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("AEGIS_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DB_URL", raising=False)
    service = RuntimeHealthService(config={"runtime": {}, "services": {}})
    monkeypatch.setattr(service, "_check_database", lambda: {"status": "error", "detail": "POSTGRES_DSN not configured"})
    monkeypatch.setattr(service, "_check_redis", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_gpu", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_storage", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_security", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_open_vocab", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_segmentation", lambda: {"status": "healthy", "detail": None})
    monkeypatch.setattr(service, "_check_identity", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_case_management", lambda: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(service, "_check_llm", lambda: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(service, "_check_osint_enrichment", lambda: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(service, "_check_streaming", lambda: {"enabled": False, "status": "disabled", "missing_dependencies": []})
    monkeypatch.setattr(service, "_check_analytics", lambda: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(
        service,
        "_check_persistence",
        lambda: {
            "enabled": True,
            "status": "failed",
            "stores": {},
            "failures": ["POSTGRES_DSN missing while production persistence requires PostgreSQL"],
            "warnings": [],
        },
    )

    readiness = service.is_ready()
    assert readiness["ready"] is False
    assert any("POSTGRES_DSN missing" in item for item in readiness["failures"])


def test_production_audit_write_failure_raises(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    service = AuditLogService(config={"enabled": True, "hash_chain_enabled": True}, repository=_BrokenAuditRepository())

    with pytest.raises(RuntimeError, match="required in production"):
        service.record("access_denied", resource_type="case", resource_id="case_1", success=False)
