from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CaseStatus = Literal["open", "investigating", "resolved", "dismissed", "archived"]
CasePriority = Literal["low", "medium", "high", "critical"]
CaseSeverity = Literal["low", "medium", "high", "critical"]
CaseReviewStatus = Literal["pending", "in_review", "reviewed", "dismissed"]
CaseEvidenceType = Literal[
    "event",
    "frame",
    "clip",
    "detection",
    "anomaly",
    "identity",
    "segmentation",
    "note",
    "external_link",
    "attachment",
    "system_report",
]

CASE_STATUSES = ("open", "investigating", "resolved", "dismissed", "archived")
CASE_PRIORITIES = ("low", "medium", "high", "critical")
CASE_SEVERITIES = ("low", "medium", "high", "critical")
CASE_REVIEW_STATUSES = ("pending", "in_review", "reviewed", "dismissed")
CASE_EVIDENCE_TYPES = (
    "event",
    "frame",
    "clip",
    "detection",
    "anomaly",
    "identity",
    "segmentation",
    "note",
    "external_link",
    "attachment",
    "system_report",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _coerce_json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _coerce_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _coerce_json_safe(item) for key, item in value.items()}


class CaseBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("metadata", mode="before", check_fields=False)
    @classmethod
    def _validate_metadata(cls, value: Any) -> dict[str, Any]:
        return _coerce_metadata(value)

    @field_validator(
        "status",
        "priority",
        "severity",
        "review_status",
        "evidence_type",
        "format",
        "report_type",
        "integrity_status",
        "type",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def _lower_str_fields(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator(
        "source_event_ids",
        "camera_ids",
        "track_ids",
        "tags",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def _listify(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            items = value
        else:
            items = [value]
        unique: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            unique.append(text)
        return unique


class CaseRecord(CaseBaseModel):
    case_id: str = Field(default_factory=lambda: _gen_id("case"))
    title: str
    description: str = ""
    status: CaseStatus = "open"
    priority: CasePriority = "medium"
    severity: CaseSeverity = "medium"
    source_event_ids: list[str] = Field(default_factory=list)
    camera_ids: list[str] = Field(default_factory=list)
    track_ids: list[str] = Field(default_factory=list)
    assigned_to: str | None = None
    created_by: str = "system"
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    closed_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    requires_review: bool = True
    review_status: CaseReviewStatus = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_closed_at(self) -> "CaseRecord":
        if self.status in {"resolved", "dismissed", "archived"} and self.closed_at is None:
            self.closed_at = self.updated_at
        if self.status in {"open", "investigating"} and self.closed_at is not None:
            self.closed_at = None
        return self


class CaseCreateRequest(CaseBaseModel):
    title: str
    description: str = ""
    priority: CasePriority = "medium"
    severity: CaseSeverity = "medium"
    source_event_ids: list[str] = Field(default_factory=list)
    camera_ids: list[str] = Field(default_factory=list)
    track_ids: list[str] = Field(default_factory=list)
    assigned_to: str | None = None
    tags: list[str] = Field(default_factory=list)
    requires_review: bool = True
    review_status: CaseReviewStatus = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseUpdateRequest(CaseBaseModel):
    title: str | None = None
    description: str | None = None
    status: CaseStatus | None = None
    priority: CasePriority | None = None
    severity: CaseSeverity | None = None
    source_event_ids: list[str] | None = None
    camera_ids: list[str] | None = None
    track_ids: list[str] | None = None
    assigned_to: str | None = None
    closed_at: str | None = None
    tags: list[str] | None = None
    requires_review: bool | None = None
    review_status: CaseReviewStatus | None = None
    metadata: dict[str, Any] | None = None


class CaseEvidence(CaseBaseModel):
    evidence_id: str = Field(default_factory=lambda: _gen_id("evi"))
    case_id: str
    evidence_type: CaseEvidenceType
    title: str = ""
    description: str = ""
    source_event_id: str | None = None
    camera_id: str | None = None
    track_ids: list[str] = Field(default_factory=list)
    storage_uri: str | None = None
    snapshot_uri: str | None = None
    created_by: str = "system"
    created_at: str = Field(default_factory=_now_iso)
    timestamp: str = Field(default_factory=_now_iso)
    hash_sha256: str | None = None
    hash_verified: bool | None = None
    integrity_status: str = "not_applicable"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseEvidenceCreateRequest(CaseBaseModel):
    evidence_type: CaseEvidenceType
    title: str = ""
    description: str = ""
    source_event_id: str | None = None
    camera_id: str | None = None
    track_ids: list[str] = Field(default_factory=list)
    storage_uri: str | None = None
    snapshot_uri: str | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseNote(CaseBaseModel):
    note_id: str = Field(default_factory=lambda: _gen_id("note"))
    case_id: str
    note: str
    created_by: str = "system"
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseNoteCreateRequest(CaseBaseModel):
    note: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseAssignment(CaseBaseModel):
    assignment_id: str = Field(default_factory=lambda: _gen_id("asg"))
    case_id: str
    assigned_to: str
    assigned_by: str = "system"
    assigned_at: str = Field(default_factory=_now_iso)
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseTimelineItem(CaseBaseModel):
    timeline_id: str = Field(default_factory=lambda: _gen_id("tl"))
    case_id: str
    timestamp: str = Field(default_factory=_now_iso)
    type: str
    title: str
    description: str = ""
    severity: CaseSeverity | None = None
    source_id: str | None = None
    sequence: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseAuditLog(CaseBaseModel):
    audit_id: str = Field(default_factory=lambda: _gen_id("caudit"))
    case_id: str
    action: str
    actor: str = "system"
    timestamp: str = Field(default_factory=_now_iso)
    detail: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseReport(CaseBaseModel):
    report_id: str = Field(default_factory=lambda: _gen_id("report"))
    case_id: str
    generated_at: str = Field(default_factory=_now_iso)
    generated_by: str = "system"
    case: dict[str, Any]
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)
    audit_summary: list[dict[str, Any]] = Field(default_factory=list)
    model_caveats: list[str] = Field(default_factory=list)
    operator_review_caveat: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseExport(CaseBaseModel):
    export_id: str = Field(default_factory=lambda: _gen_id("export"))
    case_id: str
    format: Literal["json", "markdown"]
    report_type: str = "case_export"
    content: str
    generated_at: str = Field(default_factory=_now_iso)
    generated_by: str = "system"
    artifact_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
