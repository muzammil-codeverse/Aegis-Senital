from __future__ import annotations

from app.repositories.audit_repository import JsonlAuditLogRepository
from app.repositories.case_repository import JsonlCaseRepository
from app.repositories.osint_repository import JsonlOsintRepository
from app.repositories.stream_replay_repository import JsonlStreamReplayRepository


def _case_config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


def _osint_config(tmp_path):
    return {
        "osint_enrichment": {
            "enabled": True,
            "mode": "analyst_provided_only",
            "storage": {"jsonl_dir": str(tmp_path / "osint")},
        }
    }


def test_case_repository_health_is_healthy_in_development(tmp_path, monkeypatch):
    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    health = JsonlCaseRepository(config=_case_config(tmp_path)).health_check().to_dict()
    assert health["store"] == "cases"
    assert health["backend"] == "jsonl"
    assert health["status"] == "healthy"


def test_production_jsonl_fallback_is_flagged_for_required_store(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    health = JsonlOsintRepository(config=_osint_config(tmp_path)).health_check().to_dict()
    assert health["backend"] == "jsonl"
    assert health["status"] == "failed"


def test_audit_and_replay_health_report_store_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    audit = JsonlAuditLogRepository(config={"enabled": True, "storage_dir": str(tmp_path / "audit")})
    replay = JsonlStreamReplayRepository(str(tmp_path / "replay"))

    assert audit.health_check().to_dict()["backend"] == "jsonl"
    assert replay.health_check().to_dict()["store"] == "stream_replay_metadata"
