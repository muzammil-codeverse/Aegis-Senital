from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    id: str
    label: str


class LlmRequestBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    escalate: bool = False
    operator_instructions: str = ""
    final_quality: bool = False

    @field_validator("operator_instructions", mode="before")
    @classmethod
    def _normalize_instructions(cls, value: Any) -> str:
        return str(value or "").strip()


class LlmSummaryRequest(LlmRequestBase):
    summary_kind: Literal["case_summary", "incident_summary"] = "case_summary"


class LlmTimelineSummaryRequest(LlmRequestBase):
    pass


class LlmEvidenceSummaryRequest(LlmRequestBase):
    evidence_ids: list[str] = Field(default_factory=list)


class LlmReportRequest(LlmRequestBase):
    report_kind: Literal["draft_case_report", "operator_handoff_report"] = "draft_case_report"
    format: Literal["markdown"] = "markdown"


class LlmQueryRequest(LlmRequestBase):
    question: str

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("question is required")
        return text


class LlmVerifyProviderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str | None = None


class LlmGeneratedOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    output_id: str = Field(default_factory=lambda: _gen_id("llm"))
    case_id: str | None = None
    task_type: str
    content: str
    caveat: str
    sources: list[SourceReference] = Field(default_factory=list)
    provider: str
    model: str
    reasoning_effort: str
    generated_at: str = Field(default_factory=_now_iso)
    used_fallback: bool = False
    safety_check_passed: bool = True
    report_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
