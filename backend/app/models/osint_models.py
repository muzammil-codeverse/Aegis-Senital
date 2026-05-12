from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SourceType = Literal["external_link", "uploaded_document", "uploaded_image", "analyst_note", "manual_metadata"]
SourceReliabilityLabel = Literal["unknown", "low", "medium", "high"]


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


class OsintBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("metadata", mode="before", check_fields=False)
    @classmethod
    def _validate_metadata(cls, value: Any) -> dict[str, Any]:
        return _coerce_metadata(value)

    @field_validator("source_type", "source_reliability", mode="before", check_fields=False)
    @classmethod
    def _lower_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("key_points", "limitations", "source_ids", mode="before", check_fields=False)
    @classmethod
    def _normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        items = value if isinstance(value, (list, tuple, set)) else [value]
        result: list[str] = []
        for item in items:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result


class CaseExternalSource(OsintBaseModel):
    source_id: str = Field(default_factory=lambda: _gen_id("src"))
    case_id: str
    source_type: SourceType
    title: str = ""
    url: str | None = None
    storage_uri: str | None = None
    original_filename: str | None = None
    safe_filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    hash_sha256: str | None = None
    hash_verified: bool | None = None
    integrity_status: str = "not_applicable"
    last_verified_at: str | None = None
    description: str = ""
    source_reliability: SourceReliabilityLabel = "unknown"
    analyst_provided: bool = True
    created_by: str = "system"
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    requires_review: bool = True


class CaseExternalSourceCreateRequest(OsintBaseModel):
    source_type: SourceType
    title: str = ""
    url: str | None = None
    description: str = ""
    source_reliability: SourceReliabilityLabel = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseExternalSourceUpdateRequest(OsintBaseModel):
    title: str | None = None
    url: str | None = None
    description: str | None = None
    source_reliability: SourceReliabilityLabel | None = None
    metadata: dict[str, Any] | None = None
    summary: str | None = None
    requires_review: bool | None = None


class CaseDocumentUpload(OsintBaseModel):
    upload_id: str = Field(default_factory=lambda: _gen_id("upl"))
    source_id: str
    case_id: str
    filename: str
    original_filename: str
    safe_filename: str
    storage_uri: str
    content_type: str | None = None
    extension: str
    size_bytes: int
    hash_sha256: str
    sha256: str
    hash_verified: bool = True
    integrity_status: str = "verified"
    last_verified_at: str = Field(default_factory=_now_iso)
    created_by: str = "system"
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseDocumentSummary(OsintBaseModel):
    summary_id: str = Field(default_factory=lambda: _gen_id("osum"))
    case_id: str
    source_ids: list[str] = Field(default_factory=list)
    summary: str
    key_points: list[str] = Field(default_factory=list)
    source_references: list[dict[str, str]] = Field(default_factory=list)
    operator_review_caveat: str
    limitations: list[str] = Field(default_factory=list)
    provider: str = "local_stub"
    model: str = "local_stub"
    created_by: str = "system"
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseEnrichmentSummaryRequest(OsintBaseModel):
    source_ids: list[str] = Field(default_factory=list)
    operator_instructions: str = ""
    escalate: bool = False

    @field_validator("operator_instructions", mode="before")
    @classmethod
    def _normalize_operator_instructions(cls, value: Any) -> str:
        return str(value or "").strip()


class CaseSourceReliability(OsintBaseModel):
    reliability_id: str = Field(default_factory=lambda: _gen_id("rel"))
    source_id: str
    case_id: str
    source_reliability: SourceReliabilityLabel = "unknown"
    note: str = ""
    updated_by: str = "system"
    updated_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseEnrichmentNote(OsintBaseModel):
    note_id: str = Field(default_factory=lambda: _gen_id("enote"))
    case_id: str
    source_id: str | None = None
    note: str
    created_by: str = "system"
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseEnrichmentTimelineItem(OsintBaseModel):
    enrichment_timeline_id: str = Field(default_factory=lambda: _gen_id("etl"))
    case_id: str
    source_id: str | None = None
    summary_id: str | None = None
    timestamp: str = Field(default_factory=_now_iso)
    type: str
    title: str
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseEnrichmentAuditLog(OsintBaseModel):
    enrichment_audit_id: str = Field(default_factory=lambda: _gen_id("eaudit"))
    case_id: str
    source_id: str | None = None
    action: str
    actor: str = "system"
    timestamp: str = Field(default_factory=_now_iso)
    detail: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
