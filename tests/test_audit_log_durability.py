from __future__ import annotations

from app.repositories.audit_repository import JsonlAuditLogRepository
from app.services.audit_log_service import AuditLogService


def test_audit_log_persists_denied_access_action(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    repository = JsonlAuditLogRepository(config={"enabled": True, "storage_dir": str(tmp_path / "audit")})
    service = AuditLogService(config={"enabled": True, "hash_chain_enabled": True}, repository=repository)

    service.record(
        "access_denied",
        resource_type="case",
        resource_id="case_001",
        success=False,
        detail="Object access denied",
        metadata={"reason": "scope_mismatch"},
    )

    entries = service.list_logs(action="access_denied", limit=10)
    integrity = service.verify_integrity()

    assert len(entries) == 1
    assert entries[0]["action"] == "access_denied"
    assert entries[0]["success"] is False
    assert integrity["status"] == "ok"
