from __future__ import annotations

from app.repositories.identity_repository import JsonlIdentityRepository
from inference.identity.global_identity_registry import GlobalIdentityRegistry


def test_identity_registry_survives_restart_in_development(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    original_instance = GlobalIdentityRegistry._instance
    try:
        GlobalIdentityRegistry._instance = None
        repo = JsonlIdentityRepository({"store_dir": str(tmp_path / "identities")})
        registry = GlobalIdentityRegistry(repository=repo)
        registry.register_identity(
            "cam_01",
            [1.0, 0.0],
            "gid_persist_1",
            confidence=0.93,
            source_scores={"face": 0.95, "reid": 0.88, "track": 0.72},
            source="face",
        )

        GlobalIdentityRegistry._instance = None
        restarted_repo = JsonlIdentityRepository({"store_dir": str(tmp_path / "identities")})
        restarted = GlobalIdentityRegistry(repository=restarted_repo)
        record = restarted.get_identity_record("gid_persist_1")
        observations = restarted_repo.list_observations(global_identity_id="gid_persist_1")

        assert record is not None
        assert record["global_id"] == "gid_persist_1"
        assert "cam_01" in record["cameras_seen"]
        assert observations
    finally:
        GlobalIdentityRegistry._instance = original_instance
