#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.persistence import backup_output_dir, backup_settings, latest_backup_manifest
from app.services.audit_log_service import get_audit_log_service
from app.services.case_service import get_case_service
from app.services.evidence_retention_service import get_evidence_retention_service
from app.services.osint_service import get_osint_service
from app.services.replay_clip_service import get_replay_clip_service
from inference.identity.global_identity_registry import get_global_registry
from inference.monitoring.metrics import get_metrics
from inference.open_vocab.result_store import OpenVocabResultStore


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _now_utc().strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def _collect_backup_sources() -> list[tuple[Path, Path]]:
    sources: list[tuple[Path, Path]] = []
    runtime_config_dir = ROOT / "configs" / "runtime"
    if runtime_config_dir.exists():
        for source in sorted(runtime_config_dir.glob("*.yaml")):
            sources.append((source, Path("configs") / "runtime" / source.name))

    registry_path = ROOT / "models" / "registry.json"
    if registry_path.exists():
        sources.append((registry_path, Path("registry") / "models_registry.json"))

    json_patterns = (
        "storage/cases/*.jsonl",
        "storage/osint/*.jsonl",
        "storage/audit/*.jsonl",
        "storage/open_vocab/*.jsonl",
        "storage/identities/*.jsonl",
        "storage/replay/**/*.json",
        "storage/replay/**/*.jsonl",
        "storage/retention_actions.jsonl",
    )
    for pattern in json_patterns:
        for source in sorted(ROOT.glob(pattern)):
            if source.is_file():
                sources.append((source, Path("jsonl") / _relative(source)))
    return sources


def _snapshot_cases() -> dict[str, Any]:
    service = get_case_service()
    cases = [item.model_dump(mode="json") for item in service.list_cases({"limit": 5000})]
    evidence = []
    notes = []
    audits = []
    reports = []
    for case in cases:
        case_id = str(case.get("case_id") or "")
        evidence.extend(item.model_dump(mode="json") for item in service.list_evidence(case_id))
        notes.extend(item.model_dump(mode="json") for item in service.list_notes(case_id))
        audits.extend(item.model_dump(mode="json") for item in service.repository.list_audit_logs(case_id))
        reports.extend(item.model_dump(mode="json") for item in service.repository.list_reports(case_id))
    return {
        "cases": cases,
        "evidence": evidence,
        "notes": notes,
        "audit_logs": audits,
        "reports": reports,
        "file_manifest": [
            {
                "case_id": item.get("case_id"),
                "evidence_id": item.get("evidence_id"),
                "storage_uri": item.get("storage_uri"),
                "original_filename": item.get("original_filename"),
                "safe_filename": item.get("safe_filename"),
                "content_type": item.get("content_type"),
                "size_bytes": item.get("size_bytes"),
                "hash_sha256": item.get("hash_sha256"),
                "chain_status": item.get("chain_status"),
            }
            for item in evidence
            if item.get("storage_uri")
        ],
    }


def _snapshot_osint(case_ids: list[str]) -> dict[str, Any]:
    service = get_osint_service()
    sources = []
    summaries = []
    audits = []
    for case_id in case_ids:
        sources.extend(item.model_dump(mode="json") for item in service.list_sources(case_id))
        summaries.extend(item.model_dump(mode="json") for item in service.list_summaries(case_id))
        audits.extend(item.model_dump(mode="json") for item in service.list_audit_logs(case_id))
    return {
        "sources": sources,
        "summaries": summaries,
        "audit_logs": audits,
        "file_manifest": [
            {
                "case_id": item.get("case_id"),
                "source_id": item.get("source_id"),
                "storage_uri": item.get("storage_uri"),
                "original_filename": item.get("original_filename"),
                "safe_filename": item.get("safe_filename"),
                "content_type": item.get("content_type"),
                "size_bytes": item.get("size_bytes"),
                "hash_sha256": item.get("hash_sha256"),
            }
            for item in sources
            if item.get("storage_uri")
        ],
    }


def _snapshot_identity() -> dict[str, Any]:
    registry = get_global_registry()
    repository = getattr(registry, "_repository", None)
    observations = repository.list_observations(limit=5000) if repository is not None else []
    return {
        "global_identities": registry.list_records(limit=5000),
        "observations": observations,
    }


def _snapshot_runtime_metadata() -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    payload: dict[str, Any] = {}

    try:
        case_snapshot = _snapshot_cases()
        payload["cases.json"] = case_snapshot
        case_ids = [str(item.get("case_id") or "") for item in case_snapshot.get("cases", []) if item.get("case_id")]
    except Exception as exc:
        case_ids = []
        errors.append(f"cases: {exc}")
        payload["cases.json"] = {"cases": [], "evidence": [], "notes": [], "audit_logs": [], "reports": [], "file_manifest": []}

    try:
        payload["osint.json"] = _snapshot_osint(case_ids)
    except Exception as exc:
        errors.append(f"osint: {exc}")
        payload["osint.json"] = {"sources": [], "summaries": [], "audit_logs": [], "file_manifest": []}

    try:
        payload["identity_registry.json"] = _snapshot_identity()
    except Exception as exc:
        errors.append(f"identity_registry: {exc}")
        payload["identity_registry.json"] = {"global_identities": [], "observations": []}

    try:
        payload["audit_logs.json"] = {
            "entries": get_audit_log_service().list_logs(limit=5000),
        }
    except Exception as exc:
        errors.append(f"audit_logs: {exc}")
        payload["audit_logs.json"] = {"entries": []}

    try:
        payload["open_vocab_results.json"] = {
            "items": OpenVocabResultStore().list_recent(limit=1000),
        }
    except Exception as exc:
        errors.append(f"open_vocab_results: {exc}")
        payload["open_vocab_results.json"] = {"items": []}

    try:
        repository = getattr(get_replay_clip_service(), "_repository", None)
        items = repository.list_recent(limit=1000) if repository is not None else []
        payload["stream_replay_metadata.json"] = {"items": items}
    except Exception as exc:
        errors.append(f"stream_replay_metadata: {exc}")
        payload["stream_replay_metadata.json"] = {"items": []}

    try:
        payload["retention_actions.json"] = {
            "items": get_evidence_retention_service().list_actions(limit=5000),
        }
    except Exception as exc:
        errors.append(f"retention_actions: {exc}")
        payload["retention_actions.json"] = {"items": []}

    try:
        payload["analytics_metadata.json"] = {
            "metrics": get_metrics().snapshot(),
            "last_backup_at": (latest_backup_manifest() or {}).get("created_at"),
        }
    except Exception as exc:
        errors.append(f"analytics_metadata: {exc}")
        payload["analytics_metadata.json"] = {"metrics": {}, "last_backup_at": None}

    return payload, errors


def create_backup(*, apply: bool = False, output_root: str | None = None) -> dict[str, Any]:
    settings = backup_settings()
    backup_root = Path(output_root).resolve() if output_root else backup_output_dir()
    backup_dir = backup_root / f"backup_{_timestamp()}"
    sources = _collect_backup_sources()
    metadata_snapshots, errors = _snapshot_runtime_metadata()
    plan = {
        "status": "planned" if not apply else "ready",
        "dry_run": not apply,
        "backup_dir": str(backup_dir),
        "copy_files": [{"source": str(source), "destination": str(destination)} for source, destination in sources],
        "metadata_files": sorted(metadata_snapshots.keys()),
        "error_count": len(errors),
        "errors": errors,
    }
    if not apply:
        return plan

    backup_dir.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}
    copied_files: list[str] = []

    for source, destination in sources:
        target = backup_dir / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rel = str(target.relative_to(backup_dir))
        checksums[rel] = _sha256(target)
        copied_files.append(rel)

    for name, payload in metadata_snapshots.items():
        target = backup_dir / "metadata" / name
        _write_json(target, payload)
        rel = str(target.relative_to(backup_dir))
        checksums[rel] = _sha256(target)
        copied_files.append(rel)

    checksums_path = backup_dir / "checksums.json"
    _write_json(checksums_path, checksums)

    manifest = {
        "created_at": _now_utc().isoformat(),
        "backup_dir": str(backup_dir),
        "backup_root": str(backup_root),
        "include_jsonl": bool(settings.get("include_jsonl", True)),
        "include_configs": bool(settings.get("include_configs", True)),
        "include_metadata_only_for_files": bool(settings.get("include_metadata_only_for_files", True)),
        "file_count": len(copied_files),
        "copied_files": copied_files,
        "metadata_files": sorted(metadata_snapshots.keys()),
        "errors": errors,
        "checksums_file": "checksums.json",
    }
    manifest_path = backup_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    checksums["manifest.json"] = _sha256(manifest_path)
    _write_json(checksums_path, checksums)

    return {
        "status": "created",
        "dry_run": False,
        "backup_dir": str(backup_dir),
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up runtime metadata without copying raw evidence or model binaries.")
    parser.add_argument("--apply", action="store_true", help="Create the backup. Without this flag the script performs a dry run.")
    parser.add_argument("--output-dir", default=None, help="Override the configured backup root directory.")
    args = parser.parse_args()
    result = create_backup(apply=bool(args.apply), output_root=args.output_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
