import json

import pytest

from app.repositories.model_registry_repository import FileModelRegistryRepository


def test_model_registry_repository_reads_file_snapshot(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "weapon_detector": {
                    "v1": {
                        "model_name": "weapon_detector",
                        "version": "v1",
                        "path": "models/weapon/current.pt",
                    }
                },
                "phone_detector": {
                    "v1": {
                        "model_name": "phone_detector",
                        "version": "v1",
                        "path": "models/phone/current.pt",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    repository = FileModelRegistryRepository(str(registry_path))
    entries = repository.list_entries()

    assert len(entries) == 2
    assert repository.grouped_entries()["weapon_detector"]["v1"]["path"] == "models/weapon/current.pt"


def test_model_registry_repository_prohibits_writes(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text("{}", encoding="utf-8")
    repository = FileModelRegistryRepository(str(registry_path))

    with pytest.raises(RuntimeError):
        repository.upsert_entries([])
