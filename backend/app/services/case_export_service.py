from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.case_models import CaseExport, CaseReport
from app.repositories.case_repository import CaseRepository, get_case_repository
from app.services.chain_of_custody_service import ChainOfCustodyService
from app.services.evidence_integrity import safe_evidence_metadata
from app.services.case_timeline_service import CaseTimelineService


DEFAULT_MODEL_CAVEATS = [
    "Automated detections are decision-support signals and require operator review.",
    "Possible identity matches require operator validation before operational use.",
    "Segmentation and anomaly metadata may be partial when upstream assets are unavailable.",
]

DEFAULT_OPERATOR_REVIEW_CAVEAT = (
    "This report is an automated decision-support draft based on available system evidence. "
    "It requires operator review and must not be treated as a final attribution, identity confirmation, or criminality determination."
)


class CaseExportService:
    def __init__(
        self,
        repository: CaseRepository | None = None,
        timeline_service: CaseTimelineService | None = None,
        chain_service: ChainOfCustodyService | None = None,
    ) -> None:
        self._repository = repository or get_case_repository()
        self._timeline_service = timeline_service or CaseTimelineService(self._repository)
        self._chain_service = chain_service or ChainOfCustodyService(repository=self._repository)
        storage_dir = getattr(self._repository, "_storage_dir", None)
        if storage_dir is not None:
            self._export_dir = Path(storage_dir).resolve() / "exports"
        else:
            self._export_dir = Path(__file__).resolve().parents[3] / "storage" / "cases" / "exports"
        self._export_dir.mkdir(parents=True, exist_ok=True)

    def build_report(self, case_id: str, generated_by: str = "system") -> CaseReport:
        case = self._repository.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        timeline = self._timeline_service.build_timeline(case_id)
        evidence = self._repository.list_evidence(case_id)
        notes = self._repository.list_notes(case_id)
        audit_summary = self._repository.list_audit_logs(case_id)
        enrichment_sources, enrichment_summaries = self._load_enrichment(case_id)
        manifest = self._chain_service.build_manifest(case_id, generated_by=generated_by)
        return CaseReport(
            case_id=case_id,
            generated_by=generated_by,
            case=case.model_dump(mode="json"),
            timeline=[item.model_dump(mode="json") for item in timeline],
            evidence=[item.model_dump(mode="json") for item in evidence],
            notes=[item.model_dump(mode="json") for item in notes],
            audit_summary=[item.model_dump(mode="json") for item in audit_summary],
            enrichment_sources=enrichment_sources,
            enrichment_summaries=enrichment_summaries,
            chain_of_custody_manifest=manifest.model_dump(mode="json"),
            model_caveats=list(DEFAULT_MODEL_CAVEATS),
            operator_review_caveat=DEFAULT_OPERATOR_REVIEW_CAVEAT,
            metadata={
                "assigned_to": case.assigned_to,
                "status": case.status,
                "enrichment_source_count": len(enrichment_sources),
                "enrichment_summary_count": len(enrichment_summaries),
                "evidence_manifest_items": len(manifest.evidence_items),
            },
        )

    def export_case(self, case_id: str, format: str = "json", generated_by: str = "system") -> CaseExport:
        lowered_format = str(format).lower()
        if lowered_format not in {"json", "markdown"}:
            raise ValueError(f"Unsupported case export format '{format}'")
        report = self.build_report(case_id, generated_by=generated_by)
        if lowered_format == "json":
            content = json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True)
        else:
            content = self._render_markdown(report)
        export = CaseExport(
            case_id=case_id,
            format=lowered_format,
            report_type="case_export",
            content=content,
            generated_by=generated_by,
            content_type="application/json" if lowered_format == "json" else "text/markdown",
            metadata={
                "report_id": report.report_id,
                "evidence_manifest": report.chain_of_custody_manifest or {},
            },
        )
        target_dir = (self._export_dir / case_id).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".json" if lowered_format == "json" else ".md"
        target_path = (target_dir / f"{export.export_id}{suffix}").resolve()
        target_path.write_text(content, encoding="utf-8")
        digest = _compute_sha256_bytes(content.encode("utf-8"))
        try:
            export.artifact_uri = str(target_path.relative_to(Path(__file__).resolve().parents[3]).as_posix())
        except ValueError:
            export.artifact_uri = str(target_path)
        export.size_bytes = target_path.stat().st_size
        export.hash_sha256 = digest
        export.hash_verified = True
        export.integrity_status = "verified"
        export.last_verified_at = export.generated_at
        self._repository.add_report(export)
        return export

    @staticmethod
    def _render_markdown(report: CaseReport) -> str:
        case = report.case
        evidence = report.evidence
        notes = report.notes
        audit_summary = report.audit_summary
        timeline = report.timeline
        enrichment_sources = report.enrichment_sources
        enrichment_summaries = report.enrichment_summaries

        lines = [
            f"# Case Report: {case.get('title', report.case_id)}",
            "",
            "## Case Metadata",
            f"- Case ID: {case.get('case_id')}",
            f"- Status: {case.get('status')}",
            f"- Priority: {case.get('priority')}",
            f"- Severity: {case.get('severity')}",
            f"- Assigned Operator: {case.get('assigned_to') or 'Unassigned'}",
            f"- Created By: {case.get('created_by')}",
            f"- Created At: {case.get('created_at')}",
            f"- Updated At: {case.get('updated_at')}",
            "",
            "## Summary",
            case.get("description") or "No operator summary provided.",
            "",
            "## Timeline",
        ]
        for item in timeline:
            lines.append(
                f"- {item.get('timestamp')}: {item.get('title')} - {item.get('description') or 'No detail provided.'}"
            )

        lines.extend(["", "## Evidence"])
        if evidence:
            for item in evidence:
                lines.append(
                    f"- {item.get('evidence_type')} | {item.get('timestamp') or item.get('created_at')} | "
                    f"{item.get('title') or item.get('source_event_id') or item.get('evidence_id')}"
                )
        else:
            lines.append("- No evidence items recorded.")

        lines.extend(["", "## Notes"])
        if notes:
            for item in notes:
                lines.append(f"- {item.get('created_at')} | {item.get('created_by')}: {item.get('note')}")
        else:
            lines.append("- No operator notes recorded.")

        lines.extend(["", "## Analyst-Provided Enrichment"])
        if enrichment_sources:
            for item in enrichment_sources:
                lines.append(
                    f"- {item.get('source_id')} | {item.get('source_type')} | "
                    f"{item.get('title') or 'Manual source'} | reliability={item.get('source_reliability')}"
                )
        else:
            lines.append("- No analyst-provided enrichment sources recorded.")

        lines.extend(["", "## Enrichment Summaries"])
        if enrichment_summaries:
            for item in enrichment_summaries:
                lines.append(
                    f"- {item.get('summary_id')} | {item.get('created_at')} | "
                    f"{item.get('summary') or 'No summary text provided.'}"
                )
        else:
            lines.append("- No enrichment summaries recorded.")

        lines.extend(["", "## Audit Summary"])
        if audit_summary:
            for item in audit_summary:
                lines.append(
                    f"- {item.get('timestamp')} | {item.get('actor')} | {item.get('action')} | {item.get('detail') or 'Recorded'}"
                )
        else:
            lines.append("- No case audit entries recorded.")

        manifest = report.chain_of_custody_manifest or {}
        lines.extend(["", "## Chain Of Custody"])
        if manifest.get("evidence_items"):
            for item in manifest["evidence_items"]:
                lines.append(
                    f"- {item.get('evidence_id')} | {item.get('type')} | "
                    f"{item.get('filename') or 'n/a'} | hash={item.get('hash_sha256') or 'missing'} | "
                    f"integrity={item.get('integrity_status') or 'pending'}"
                )
        else:
            lines.append("- No file-backed evidence items recorded.")
        audit_counts = manifest.get("audit_summary") or {}
        lines.append(
            f"- Audit counts: uploads={audit_counts.get('uploads', 0)}, downloads={audit_counts.get('downloads', 0)}, "
            f"verifications={audit_counts.get('verifications', 0)}, exports={audit_counts.get('exports', 0)}"
        )

        lines.extend(["", "## Model Caveats"])
        for caveat in report.model_caveats:
            lines.append(f"- {caveat}")

        lines.extend(["", "## Operator Review Caveat", report.operator_review_caveat])
        return "\n".join(lines)

    @staticmethod
    def _load_enrichment(case_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try:
            from app.services.osint_service import get_osint_service

            service = get_osint_service()
            if not service.health().get("enabled", False):
                return [], []
            return (
                [_export_source(item) for item in service.list_sources(case_id)],
                [_export_summary(item) for item in service.list_summaries(case_id)],
            )
        except Exception:
            return [], []


def _export_source(source: Any) -> dict[str, Any]:
    metadata = safe_evidence_metadata(getattr(source, "metadata", {}) or {})
    return {
        "source_id": getattr(source, "source_id", None),
        "source_type": getattr(source, "source_type", None),
        "title": str(getattr(source, "title", "") or "").strip(),
        "description": str(getattr(source, "description", "") or "").strip(),
        "url": getattr(source, "url", None),
        "original_filename": getattr(source, "original_filename", None),
        "safe_filename": getattr(source, "safe_filename", None),
        "content_type": getattr(source, "content_type", None),
        "size_bytes": getattr(source, "size_bytes", None),
        "hash_sha256": getattr(source, "hash_sha256", None),
        "integrity_status": getattr(source, "integrity_status", "not_applicable"),
        "source_reliability": getattr(source, "source_reliability", "unknown"),
        "analyst_provided": bool(getattr(source, "analyst_provided", True)),
        "created_by": getattr(source, "created_by", None),
        "created_at": getattr(source, "created_at", None),
        "summary": str(getattr(source, "summary", "") or "").strip() or None,
        "requires_review": bool(getattr(source, "requires_review", True)),
        "metadata": metadata,
        "has_storage_artifact": bool(getattr(source, "storage_uri", None)),
    }


def _export_summary(summary: Any) -> dict[str, Any]:
    return {
        "summary_id": getattr(summary, "summary_id", None),
        "case_id": getattr(summary, "case_id", None),
        "source_ids": list(getattr(summary, "source_ids", []) or []),
        "summary": str(getattr(summary, "summary", "") or "").strip(),
        "key_points": list(getattr(summary, "key_points", []) or []),
        "source_references": list(getattr(summary, "source_references", []) or []),
        "operator_review_caveat": getattr(summary, "operator_review_caveat", ""),
        "limitations": list(getattr(summary, "limitations", []) or []),
        "provider": getattr(summary, "provider", "local_stub"),
        "model": getattr(summary, "model", "local_stub"),
        "created_by": getattr(summary, "created_by", None),
        "created_at": getattr(summary, "created_at", None),
        "metadata": safe_evidence_metadata(getattr(summary, "metadata", {}) or {}),
    }


def _compute_sha256_bytes(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()
