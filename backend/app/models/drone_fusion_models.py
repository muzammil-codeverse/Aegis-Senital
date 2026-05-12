"""Pydantic models for Phase 46 — Drone + Fixed Camera Fusion.

All fusion results are candidate relationships requiring operator review.
Safe wording is mandatory: no confirmed identity, no confirmed guilt.
Simulated drone data is always labelled simulated=True.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal[
    "fixed_camera",
    "drone_simulation",
    "drone_mission",
    "uploaded_video",
]
ReviewStatus = Literal["pending", "accepted", "rejected", "inconclusive"]


SAFE_SUMMARIES = {
    "default": "Candidate cross-source observation requiring operator review.",
    "handoff": "Possible route continuation between sources. Operator review required.",
    "correlation": "Candidate cross-source match. Evidence-backed hypothesis. Operator review required.",
    "path": "Simulated aerial observation contributing to investigative path hypothesis.",
}

FORBIDDEN_PHRASES = (
    "confirmed suspect",
    "identity confirmed",
    "criminal confirmed",
    "target confirmed",
    "real drone pursuit",
    "guilty",
    "attacker confirmed",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "fusion") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _enforce_safe_wording(text: str) -> str:
    lower = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lower:
            raise ValueError(f"Forbidden phrase in fusion output: '{phrase}'")
    return text


# ---------------------------------------------------------------------------
# Source reference
# ---------------------------------------------------------------------------

class FusionSourceRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_type: SourceType
    source_id: str
    event_id: str | None = None
    session_id: str | None = None
    case_id: str | None = None
    evidence_ref_ids: list[str] = Field(default_factory=list)
    simulated: bool = False


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

class FusionObservation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    observation_id: str = Field(default_factory=lambda: _new_id("obs"))
    source_type: SourceType
    source_id: str
    event_id: str | None = None
    case_id: str | None = None
    timestamp: str = Field(default_factory=_now_iso)
    latitude: float | None = None
    longitude: float | None = None
    altitude_meters: float | None = None
    geo_missing: bool = False
    event_type: str | None = None
    severity: str | None = None
    track_id: str | None = None
    identity_candidate_id: str | None = None
    appearance_ref: str | None = None
    simulated: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    source_ref: FusionSourceRef | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Confidence breakdown
# ---------------------------------------------------------------------------

class FusionConfidenceBreakdown(BaseModel):
    model_config = ConfigDict(extra="ignore")

    time_score: float = 0.0
    geo_score: float = 0.0
    appearance_score: float = 0.0
    event_type_score: float = 0.0
    mission_context_score: float = 0.0
    weighted_total: float = 0.0


# ---------------------------------------------------------------------------
# Cross-source correlation
# ---------------------------------------------------------------------------

class CrossSourceCorrelation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    correlation_id: str = Field(default_factory=lambda: _new_id("corr"))
    primary_observation_id: str
    matched_observation_id: str
    source_pair: list[str] = Field(default_factory=list)
    confidence: float
    confidence_breakdown: FusionConfidenceBreakdown
    safe_summary: str = SAFE_SUMMARIES["correlation"]
    operator_review_required: bool = True
    review_status: ReviewStatus = "pending"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_notes: str | None = None
    case_id: str | None = None
    event_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)

    @field_validator("safe_summary")
    @classmethod
    def _validate_safe_summary(cls, v: str) -> str:
        return _enforce_safe_wording(v)


# ---------------------------------------------------------------------------
# Drone-camera handoff
# ---------------------------------------------------------------------------

class DroneCameraHandoff(BaseModel):
    model_config = ConfigDict(extra="ignore")

    handoff_id: str = Field(default_factory=lambda: _new_id("handoff"))
    from_source_type: SourceType
    from_source_id: str
    to_source_type: SourceType
    to_source_id: str
    timestamp: str = Field(default_factory=_now_iso)
    reason: str = "nearby aerial observation"
    confidence: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)
    safe_summary: str = SAFE_SUMMARIES["handoff"]
    operator_review_required: bool = True
    case_id: str | None = None
    event_id: str | None = None

    @field_validator("safe_summary")
    @classmethod
    def _validate_safe_summary(cls, v: str) -> str:
        return _enforce_safe_wording(v)


# ---------------------------------------------------------------------------
# Fusion track candidate
# ---------------------------------------------------------------------------

class FusionTrackCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str = Field(default_factory=lambda: _new_id("candidate"))
    observations: list[str] = Field(default_factory=list)
    correlations: list[str] = Field(default_factory=list)
    track_id: str | None = None
    identity_candidate_id: str | None = None
    case_id: str | None = None
    confidence: float = 0.0
    simulated: bool = False
    safe_summary: str = SAFE_SUMMARIES["default"]
    operator_review_required: bool = True

    @field_validator("safe_summary")
    @classmethod
    def _validate_safe_summary(cls, v: str) -> str:
        return _enforce_safe_wording(v)


# ---------------------------------------------------------------------------
# Fusion hypothesis
# ---------------------------------------------------------------------------

class FusionHypothesis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hypothesis_id: str = Field(default_factory=lambda: _new_id("hyp"))
    track_candidate_id: str | None = None
    case_id: str | None = None
    observations: list[str] = Field(default_factory=list)
    correlations: list[str] = Field(default_factory=list)
    handoffs: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    safe_summary: str = SAFE_SUMMARIES["path"]
    operator_review_required: bool = True
    created_at: str = Field(default_factory=_now_iso)

    @field_validator("safe_summary")
    @classmethod
    def _validate_safe_summary(cls, v: str) -> str:
        return _enforce_safe_wording(v)


# ---------------------------------------------------------------------------
# Review request/record
# ---------------------------------------------------------------------------

class FusionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["accept", "reject", "inconclusive"]
    notes: str | None = None


class FusionReviewRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    correlation_id: str
    action: Literal["accept", "reject", "inconclusive"]
    reviewed_by: str
    reviewed_at: str = Field(default_factory=_now_iso)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Fusion timeline entry
# ---------------------------------------------------------------------------

class FusionTimelineEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entry_id: str = Field(default_factory=lambda: _new_id("tle"))
    timestamp: str
    entry_type: str
    source_type: SourceType | None = None
    source_id: str | None = None
    observation_id: str | None = None
    correlation_id: str | None = None
    handoff_id: str | None = None
    confidence: float | None = None
    simulated: bool = False
    safe_summary: str | None = None
    case_id: str | None = None


class FusionTimeline(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str | None = None
    event_id: str | None = None
    entries: list[FusionTimelineEntry] = Field(default_factory=list)
    generated_at: str = Field(default_factory=_now_iso)
    operator_review_required: bool = True
    safe_summary: str = "Candidate fusion timeline. Operator review required."

    @field_validator("safe_summary")
    @classmethod
    def _validate_safe_summary(cls, v: str) -> str:
        return _enforce_safe_wording(v)


# ---------------------------------------------------------------------------
# Fusion summary report
# ---------------------------------------------------------------------------

class FusionSummaryReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    report_id: str = Field(default_factory=lambda: _new_id("rpt"))
    case_id: str | None = None
    event_id: str | None = None
    observations_count: int = 0
    correlations_count: int = 0
    handoffs_count: int = 0
    pending_reviews: int = 0
    accepted_correlations: int = 0
    rejected_correlations: int = 0
    average_confidence: float = 0.0
    sources_involved: list[str] = Field(default_factory=list)
    safe_summary: str = "Candidate cross-source fusion summary. Operator review required."
    limitations: list[str] = Field(
        default_factory=lambda: [
            "Fusion correlations are candidate relationships, not confirmed identity.",
            "Simulated drone observations are not real aircraft data.",
            "All results require operator review before investigative use.",
        ]
    )
    generated_at: str = Field(default_factory=_now_iso)

    @field_validator("safe_summary")
    @classmethod
    def _validate_safe_summary(cls, v: str) -> str:
        return _enforce_safe_wording(v)


# ---------------------------------------------------------------------------
# API request/response wrappers
# ---------------------------------------------------------------------------

class FusionCorrelateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str | None = None
    event_id: str | None = None
    time_window_seconds: int = 60
    source_types: list[SourceType] | None = None


class FusionObservationListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    observations: list[FusionObservation]
    total: int


class FusionCorrelationListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    correlations: list[CrossSourceCorrelation]
    total: int


class FusionHandoffListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    handoffs: list[DroneCameraHandoff]
    total: int


class HandoffSuggestForEventRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str
    radius_meters: float = 200.0


class HandoffSuggestForMissionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    radius_meters: float = 200.0
