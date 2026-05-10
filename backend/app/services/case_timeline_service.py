from __future__ import annotations

import hashlib
from typing import Any

from app.models.case_models import CaseTimelineItem
from app.repositories.case_repository import CaseRepository, get_case_repository


class CaseTimelineService:
    def __init__(self, repository: CaseRepository | None = None) -> None:
        self._repository = repository or get_case_repository()

    def build_timeline(self, case_id: str) -> list[CaseTimelineItem]:
        case = self._repository.get_case(case_id)
        if case is None:
            return []

        evidence_items = self._repository.list_evidence(case_id)
        notes = self._repository.list_notes(case_id)
        audit_logs = self._repository.list_audit_logs(case_id)

        items: list[CaseTimelineItem] = []
        seq = 0

        items.append(
            CaseTimelineItem(
                timeline_id=_stable_timeline_id(case_id, "case_created", case.case_id, case.created_at),
                case_id=case_id,
                timestamp=case.created_at,
                type="case_created",
                title=case.title,
                description=case.description or "Case created for operator review.",
                severity=case.severity,
                source_id=case.case_id,
                sequence=seq,
                metadata={
                    "status": case.status,
                    "priority": case.priority,
                    "created_by": case.created_by,
                    "requires_review": case.requires_review,
                },
            )
        )
        seq += 1

        covered_source_ids = {item.source_event_id for item in evidence_items if item.source_event_id}
        for source_event_id in case.source_event_ids:
            if source_event_id in covered_source_ids:
                continue
            items.append(
                CaseTimelineItem(
                    timeline_id=_stable_timeline_id(case_id, "source_event", source_event_id, case.created_at),
                    case_id=case_id,
                    timestamp=case.created_at,
                    type="source_event",
                    title="Source event linked",
                    description="Source event reference added to case.",
                    severity=case.severity,
                    source_id=source_event_id,
                    sequence=seq,
                    metadata={},
                )
            )
            seq += 1

        for evidence in evidence_items:
            items.append(
                CaseTimelineItem(
                    timeline_id=_stable_timeline_id(case_id, "evidence", evidence.evidence_id, evidence.timestamp or evidence.created_at),
                    case_id=case_id,
                    timestamp=evidence.timestamp or evidence.created_at,
                    type=evidence.evidence_type,
                    title=evidence.title or _evidence_title(evidence.evidence_type),
                    description=evidence.description or _evidence_description(evidence.metadata),
                    severity=_evidence_severity(evidence.metadata, case.severity),
                    source_id=evidence.source_event_id or evidence.evidence_id,
                    sequence=seq,
                    metadata={
                        "camera_id": evidence.camera_id,
                        "track_ids": evidence.track_ids,
                        "integrity_status": evidence.integrity_status,
                        **(evidence.metadata or {}),
                    },
                )
            )
            seq += 1

        for note in notes:
            items.append(
                CaseTimelineItem(
                    timeline_id=_stable_timeline_id(case_id, "note", note.note_id, note.created_at),
                    case_id=case_id,
                    timestamp=note.created_at,
                    type="note",
                    title=f"Operator note by {note.created_by}",
                    description=note.note,
                    severity=None,
                    source_id=note.note_id,
                    sequence=seq,
                    metadata=note.metadata,
                )
            )
            seq += 1

        for audit in audit_logs:
            if audit.action in {"evidence_added", "note_added"}:
                continue
            items.append(
                CaseTimelineItem(
                    timeline_id=_stable_timeline_id(case_id, "audit", audit.audit_id, audit.timestamp),
                    case_id=case_id,
                    timestamp=audit.timestamp,
                    type="audit",
                    title=_audit_title(audit.action),
                    description=audit.detail or _audit_description(audit.action, audit.metadata),
                    severity=None,
                    source_id=audit.audit_id,
                    sequence=seq,
                    metadata={"actor": audit.actor, **(audit.metadata or {})},
                )
            )
            seq += 1

        items.sort(key=lambda item: (_sort_key(item.timestamp), item.sequence))
        return items


def _sort_key(timestamp: str) -> float:
    from app.repositories.case_repository import _parse_timestamp  # local import to avoid duplication

    return _parse_timestamp(timestamp)


def _stable_timeline_id(case_id: str, item_type: str, source_id: str, timestamp: str) -> str:
    raw = f"{case_id}::{item_type}::{source_id}::{timestamp}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"tl_{digest}"


def _evidence_title(evidence_type: str) -> str:
    mapping = {
        "event": "Event evidence added",
        "frame": "Frame reference added",
        "clip": "Clip reference added",
        "detection": "Detection evidence added",
        "anomaly": "Possible anomaly evidence added",
        "identity": "Possible identity-match evidence added",
        "segmentation": "Segmentation evidence added",
        "external_link": "External reference added",
        "attachment": "Attachment reference added",
        "system_report": "System report attached",
    }
    return mapping.get(str(evidence_type), "Evidence item added")


def _evidence_description(metadata: dict[str, Any]) -> str:
    if not isinstance(metadata, dict):
        return "Evidence item requires operator review."
    if metadata.get("display_label"):
        return f"{metadata['display_label']}. Operator review required."
    if metadata.get("summary"):
        return str(metadata["summary"])
    if metadata.get("event_type"):
        return f"{metadata['event_type']} linked for operator review."
    return "Evidence item added to the case."


def _evidence_severity(metadata: dict[str, Any], fallback: str) -> str:
    if isinstance(metadata, dict):
        for key in ("severity", "highest_risk", "priority_level"):
            value = metadata.get(key)
            if isinstance(value, str):
                lowered = value.lower()
                if lowered in {"low", "medium", "high", "critical"}:
                    return lowered
    return fallback


def _audit_title(action: str) -> str:
    mapping = {
        "case_created": "Case created",
        "case_updated": "Case updated",
        "case_assigned": "Assignment updated",
        "status_changed": "Case status changed",
        "review_status_changed": "Review status changed",
        "case_exported": "Case exported",
        "case_archived": "Case archived",
        "case_dismissed": "Case dismissed",
        "case_reopened": "Case reopened",
        "event_linked": "Source event linked",
        "auto_deduplicated": "Related event merged",
    }
    return mapping.get(action, action.replace("_", " ").title())


def _audit_description(action: str, metadata: dict[str, Any]) -> str:
    if action == "case_assigned":
        return f"Assigned to {metadata.get('assigned_to') or 'unassigned'}."
    if action == "status_changed":
        return f"Status updated to {metadata.get('to_status') or 'updated'}."
    if action == "case_exported":
        return f"Exported as {metadata.get('format') or 'report'}."
    return "Case activity recorded."
