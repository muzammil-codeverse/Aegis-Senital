import json
import sys

from scripts import migrate_model_registry_to_db


def test_model_registry_migration_dry_run(tmp_path, capsys, monkeypatch):
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
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["migrate_model_registry_to_db.py", "--file", str(registry_path), "--dry-run"])

    result = migrate_model_registry_to_db.main()
    output = capsys.readouterr().out

    assert result == 0
    assert "Dry run only" in output
