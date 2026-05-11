#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


OVERWRITE_CONFIRMATION_TOKEN = "RESTORE_RUNTIME_METADATA"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_target(project_root: Path, relative_path: str) -> Path | None:
    rel = Path(relative_path)
    rel_text = rel.as_posix()
    if rel_text.startswith("configs/runtime/"):
        return (project_root / rel).resolve()
    if rel_text.startswith("jsonl/"):
        original = rel_text[len("jsonl/") :]
        return (project_root / original).resolve()
    if rel_text == "registry/models_registry.json":
        return (project_root / "models" / "registry.json").resolve()
    return None


def validate_backup(backup_dir: str | Path) -> dict[str, Any]:
    base = Path(backup_dir).resolve()
    manifest_path = base / "manifest.json"
    checksums_path = base / "checksums.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest missing: {manifest_path}")
    if not checksums_path.exists():
        raise FileNotFoundError(f"checksums missing: {checksums_path}")

    manifest = _load_json(manifest_path)
    checksums = _load_json(checksums_path)
    mismatches: list[str] = []
    verified: list[str] = []
    for relative_path, expected_hash in checksums.items():
        target = base / relative_path
        if not target.exists():
            mismatches.append(f"missing:{relative_path}")
            continue
        actual_hash = _sha256(target)
        if actual_hash != expected_hash:
            mismatches.append(f"checksum:{relative_path}")
            continue
        verified.append(relative_path)
    return {
        "backup_dir": str(base),
        "manifest": manifest,
        "verified_files": verified,
        "mismatches": mismatches,
        "valid": not mismatches,
    }


def restore_backup(
    backup_dir: str | Path,
    *,
    apply: bool = False,
    project_root: str | Path | None = None,
    confirm_overwrite: str | None = None,
) -> dict[str, Any]:
    validation = validate_backup(backup_dir)
    destination_root = Path(project_root).resolve() if project_root else ROOT.resolve()
    if not validation["valid"]:
        return {
            "status": "invalid",
            "dry_run": not apply,
            **validation,
        }

    copied_files = list((validation["manifest"] or {}).get("copied_files") or [])
    plan = []
    for relative_path in copied_files:
        target = _resolve_target(destination_root, relative_path)
        if target is None:
            continue
        plan.append(
            {
                "source": str(Path(backup_dir).resolve() / relative_path),
                "target": str(target),
                "exists": target.exists(),
            }
        )

    if not apply:
        return {
            "status": "validated",
            "dry_run": True,
            "project_root": str(destination_root),
            "plan": plan,
            **validation,
        }

    overwrite_required = any(item["exists"] for item in plan)
    if overwrite_required and confirm_overwrite != OVERWRITE_CONFIRMATION_TOKEN:
        raise ValueError("restore requires explicit overwrite confirmation")

    restored_files: list[str] = []
    for item in plan:
        source = Path(item["source"])
        target = Path(item["target"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        restored_files.append(str(target))

    return {
        "status": "restored",
        "dry_run": False,
        "project_root": str(destination_root),
        "restored_files": restored_files,
        **validation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and optionally restore a runtime metadata backup.")
    parser.add_argument("backup_dir", help="Path to the backup_<timestamp> directory.")
    parser.add_argument("--apply", action="store_true", help="Apply the restore. Without this flag the script performs a dry run.")
    parser.add_argument("--confirm-overwrite", default=None, help=f"Required when restoring over existing files. Use {OVERWRITE_CONFIRMATION_TOKEN}.")
    args = parser.parse_args()
    result = restore_backup(
        args.backup_dir,
        apply=bool(args.apply),
        confirm_overwrite=args.confirm_overwrite,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
