from __future__ import annotations

from pathlib import Path

import pytest

from scripts import backup_runtime_metadata as backup_script
from scripts import restore_runtime_metadata as restore_script


def test_backup_manifest_generated(tmp_path, monkeypatch):
    source = tmp_path / "storage" / "cases" / "cases.jsonl"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"case_id":"case_1"}\n', encoding="utf-8")

    monkeypatch.setattr(backup_script, "ROOT", tmp_path)
    monkeypatch.setattr(
        backup_script,
        "_collect_backup_sources",
        lambda: [(source, Path("jsonl") / "storage" / "cases" / "cases.jsonl")],
    )
    monkeypatch.setattr(
        backup_script,
        "_snapshot_runtime_metadata",
        lambda: ({"cases.json": {"cases": [{"case_id": "case_1"}]}}, []),
    )

    result = backup_script.create_backup(apply=True, output_root=str(tmp_path / "backups"))
    manifest_path = Path(result["backup_dir"]) / "manifest.json"

    assert manifest_path.exists()
    assert result["manifest"]["file_count"] >= 2


def test_restore_dry_run_validates_backup(tmp_path, monkeypatch):
    source = tmp_path / "storage" / "audit" / "audit.jsonl"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"audit_id":"1"}\n', encoding="utf-8")

    monkeypatch.setattr(backup_script, "ROOT", tmp_path)
    monkeypatch.setattr(
        backup_script,
        "_collect_backup_sources",
        lambda: [(source, Path("jsonl") / "storage" / "audit" / "audit.jsonl")],
    )
    monkeypatch.setattr(
        backup_script,
        "_snapshot_runtime_metadata",
        lambda: ({"audit_logs.json": {"entries": []}}, []),
    )

    created = backup_script.create_backup(apply=True, output_root=str(tmp_path / "backups"))
    restored = restore_script.restore_backup(
        created["backup_dir"],
        apply=False,
        project_root=tmp_path / "restore_target",
    )

    assert restored["valid"] is True
    assert restored["status"] == "validated"
    assert restored["plan"]


def test_restore_requires_explicit_overwrite_confirmation(tmp_path, monkeypatch):
    source = tmp_path / "storage" / "identities" / "global_identity_registry.jsonl"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"global_identity_id":"gid_1"}\n', encoding="utf-8")

    monkeypatch.setattr(backup_script, "ROOT", tmp_path)
    monkeypatch.setattr(
        backup_script,
        "_collect_backup_sources",
        lambda: [(source, Path("jsonl") / "storage" / "identities" / "global_identity_registry.jsonl")],
    )
    monkeypatch.setattr(
        backup_script,
        "_snapshot_runtime_metadata",
        lambda: ({"identity_registry.json": {"global_identities": []}}, []),
    )

    created = backup_script.create_backup(apply=True, output_root=str(tmp_path / "backups"))
    target = tmp_path / "restore_target" / "storage" / "identities" / "global_identity_registry.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing\n", encoding="utf-8")

    with pytest.raises(ValueError, match="explicit overwrite confirmation"):
        restore_script.restore_backup(
            created["backup_dir"],
            apply=True,
            project_root=tmp_path / "restore_target",
        )
