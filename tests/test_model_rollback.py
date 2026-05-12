import json
from pathlib import Path

import pytest

from app.repositories.model_registry_repository import FileModelRegistryRepository, reset_model_registry_repository
from app.services.model_governance_service import rollback_registry_version
from app.models.security_models import UserAccount


def test_rollback_requires_reason(tmp_path):
    reg = tmp_path / "registry.json"
    reg.write_text(
        json.dumps(
            {
                "weapon_detector": {
                    "active_version": "v2",
                    "v1": {"path": "a.pt", "model_name": "w", "version": "v1", "status": "deprecated"},
                    "v2": {"path": "b.pt", "model_name": "w", "version": "v2", "status": "active"},
                }
            }
        ),
        encoding="utf-8",
    )
    repo = FileModelRegistryRepository(str(reg), allow_writes=True)
    with pytest.raises(ValueError, match="rollback_reason_required"):
        rollback_registry_version(
            model_key="weapon_detector",
            target_version="v1",
            reason="",
            user=None,
            request=None,
        )
    reset_model_registry_repository()


def test_rollback_updates_active_pointer(tmp_path, monkeypatch):
    reg = tmp_path / "registry.json"
    snap = {
        "weapon_detector": {
            "active_version": "v2",
            "v1": {"path": "a.pt", "model_name": "w", "version": "v1", "status": "deprecated", "known_limitations": ["x"]},
            "v2": {"path": "b.pt", "model_name": "w", "version": "v2", "status": "active", "known_limitations": ["y"]},
        }
    }
    reg.write_text(json.dumps(snap), encoding="utf-8")
    repository = FileModelRegistryRepository(str(reg), allow_writes=True)

    def _fake_get(config=None):
        return repository

    monkeypatch.setattr(
        "app.services.model_governance_service.get_model_registry_repository",
        _fake_get,
    )
    reset_model_registry_repository()
    user = UserAccount(
        user_id="u1",
        username="admin",
        display_name="Admin",
        role="admin",
        status="active",
        password_hash="",
        created_at=1.0,
        updated_at=1.0,
    )
    rollback_registry_version(
        model_key="weapon_detector",
        target_version="v1",
        reason="operator regression observed",
        user=user,
        request=None,
    )
    data = json.loads(reg.read_text(encoding="utf-8"))
    assert data["weapon_detector"]["active_version"] == "v1"
    reset_model_registry_repository()
