from __future__ import annotations

from app.services.runtime_health_service import RuntimeHealthService


class _StubIdentityService:
    def get_health(self):
        return {
            "persistence": {
                "store": "identity_registry",
                "backend": "jsonl",
                "status": "healthy",
                "last_error": None,
            }
        }


class _StubAuditService:
    def health(self):
        return {
            "backend": "jsonl",
            "status": "healthy",
            "last_error": None,
        }


class _StubReplayService:
    def health_check(self):
        return {
            "backend": "jsonl",
            "status": "healthy",
            "last_error": None,
        }


class _StubRetentionService:
    def health_check(self):
        return {
            "backend": "jsonl",
            "status": "healthy",
            "last_error": None,
            "retention_mode": "dry_run",
        }


class _StubOpenVocabStore:
    def health_check(self):
        return {
            "backend": "jsonl",
            "status": "healthy",
            "last_error": None,
        }


def _minimal_runtime_state(service, monkeypatch):
    monkeypatch.setattr(service, "_check_database", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_redis", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_gpu", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_identity", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_open_vocab", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_segmentation", lambda: {"status": "healthy", "detail": None})
    monkeypatch.setattr(service, "_check_storage", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_model_registry", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_event_bus", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_security", lambda: {"status": "ok", "detail": None})
    monkeypatch.setattr(service, "_check_llm", lambda: {"enabled": False, "status": "disabled", "detail": None})
    monkeypatch.setattr(service, "_check_streaming", lambda: {"enabled": False, "status": "disabled", "missing_dependencies": []})


def test_runtime_health_reports_persistence_stores(monkeypatch):
    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    service = RuntimeHealthService(config={"runtime": {}, "services": {}})
    _minimal_runtime_state(service, monkeypatch)
    monkeypatch.setattr(service, "_check_case_management", lambda: {"enabled": True, "storage": "jsonl", "status": "healthy", "last_error": None})
    monkeypatch.setattr(service, "_check_osint_enrichment", lambda: {"enabled": True, "storage": "jsonl", "status": "healthy", "last_error": None})
    monkeypatch.setattr(service, "_check_analytics", lambda: {"enabled": True, "storage": "derived", "status": "healthy", "last_error": None})
    monkeypatch.setattr(service, "_check_event_persistence", lambda: {"store": "events", "backend": "jsonl", "status": "healthy", "last_error": None})
    monkeypatch.setattr(service, "_check_evidence_file_store", lambda: {"store": "evidence_files", "backend": "filesystem", "status": "healthy", "last_error": None})
    monkeypatch.setattr(service, "_check_model_registry_store", lambda: {"store": "model_registry", "backend": "json", "status": "healthy", "last_error": None})

    monkeypatch.setattr("app.services.identity_service.get_identity_service", lambda: _StubIdentityService())
    monkeypatch.setattr("app.services.audit_log_service.get_audit_log_service", lambda: _StubAuditService())
    monkeypatch.setattr("app.services.replay_clip_service.get_replay_clip_service", lambda: _StubReplayService())
    monkeypatch.setattr("app.services.evidence_retention_service.get_evidence_retention_service", lambda: _StubRetentionService())
    monkeypatch.setattr("inference.open_vocab.result_store.OpenVocabResultStore", lambda: _StubOpenVocabStore())
    monkeypatch.setattr("app.services.runtime_health_service.latest_backup_manifest", lambda: {"created_at": "2026-05-12T00:00:00+00:00"})

    report = service.get_health(include_sensitive=True)

    assert report["persistence"]["status"] == "healthy"
    assert report["persistence"]["stores"]["cases"]["backend"] == "jsonl"
    assert report["persistence"]["stores"]["identity_registry"]["status"] == "healthy"
    assert report["checks"]["persistence"]["retention_mode"] == "dry_run"


def test_readiness_includes_persistence_failures(monkeypatch):
    service = RuntimeHealthService(config={"runtime": {}, "services": {}})
    monkeypatch.setattr(service, "_check_database", lambda: {"status": "ok", "detail": None})
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
