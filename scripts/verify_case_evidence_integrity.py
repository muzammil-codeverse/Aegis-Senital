#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.case_service import get_case_service
from app.services.evidence_integrity import describe_local_artifact


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _render_markdown(report: dict) -> str:
    lines = [
        "# Case Evidence Integrity Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Scope: {report['scope']}",
        f"- Cases checked: {report['case_count']}",
        f"- Evidence checked: {report['evidence_count']}",
        f"- Hash mismatches: {report['hash_mismatch_count']}",
        f"- Missing files: {report['missing_file_count']}",
        "",
        "## Findings",
    ]
    if not report["results"]:
        lines.append("- No evidence items matched the requested scope.")
        return "\n".join(lines)
    for item in report["results"]:
        lines.append(
            f"- {item['case_id']} / {item['evidence_id']} | {item['integrity_status']} | "
            f"expected={item.get('expected_hash_sha256') or 'n/a'} | "
            f"computed={item.get('computed_hash_sha256') or 'n/a'}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify stored case evidence hashes and file presence.")
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--all", action="store_true", dest="all_cases")
    parser.add_argument("--repair-metadata", default="false")
    args = parser.parse_args()

    if not args.case_id and not args.all_cases:
        parser.error("Pass --case-id <id> or --all")

    service = get_case_service()
    actor = "integrity-script"
    cases = []
    if args.all_cases:
        cases = service.list_cases({"limit": 5000})
    else:
        case = service.get_case(str(args.case_id))
        if case is None:
            raise SystemExit(f"Case '{args.case_id}' not found")
        cases = [case]

    repair_metadata = _parse_bool(args.repair_metadata)
    results: list[dict] = []
    mismatch_count = 0
    missing_count = 0
    for case in cases:
        for evidence in service.list_evidence(case.case_id):
            artifact = describe_local_artifact(
                evidence.storage_uri,
                expected_hash=evidence.hash_sha256,
                content_type=evidence.content_type,
                safe_filename=evidence.safe_filename,
            )
            status = artifact.get("integrity_status") or "failed"
            if status == "hash_mismatch":
                mismatch_count += 1
            if status == "missing_file":
                missing_count += 1
            result = {
                "case_id": case.case_id,
                "evidence_id": evidence.evidence_id,
                "storage_uri": evidence.storage_uri,
                "expected_hash_sha256": evidence.hash_sha256,
                "computed_hash_sha256": artifact.get("hash_sha256"),
                "hash_verified": artifact.get("hash_verified"),
                "integrity_status": status,
                "size_bytes": artifact.get("size_bytes") or evidence.size_bytes,
                "content_type": artifact.get("content_type") or evidence.content_type,
                "last_verified_at": artifact.get("last_verified_at"),
            }
            results.append(result)
            if repair_metadata:
                service.update_evidence(
                    evidence.evidence_id,
                    {
                        "hash_sha256": evidence.hash_sha256 or artifact.get("hash_sha256"),
                        "hash_verified": artifact.get("hash_verified"),
                        "integrity_status": status,
                        "size_bytes": artifact.get("size_bytes") or evidence.size_bytes,
                        "content_type": artifact.get("content_type") or evidence.content_type,
                        "last_verified_at": artifact.get("last_verified_at"),
                    },
                    actor=actor,
                )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": args.case_id or "all",
        "repair_metadata": repair_metadata,
        "case_count": len(cases),
        "evidence_count": len(results),
        "hash_mismatch_count": mismatch_count,
        "missing_file_count": missing_count,
        "results": results,
    }

    output_dir = ROOT / "storage" / "integrity_reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    label = str(args.case_id or "all").replace("/", "_")
    json_path = output_dir / f"evidence_integrity_{label}_{stamp}.json"
    md_path = output_dir / f"evidence_integrity_{label}_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path), **{k: v for k, v in report.items() if k != "results"}}, indent=2))
    return 1 if mismatch_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
