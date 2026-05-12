from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SubjectRefType = Literal["track", "identity_candidate", "manual", "event"]
ReviewStatus = Literal["pending", "accepted", "rejected", "inconclusive"]
HypothesisStepMode = Literal["walk", "run", "vehicle", "unknown"]


class InvestigationSubjectRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: SubjectRefType = "manual"
    ref_id: str
    display_label: str | None = None


class InvestigationObservation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    observation_id: str
    camera_id: str
    timestamp: str
    event_id: str | None = None
    case_id: str | None = None
    track_id: str | None = None
    identity_candidate_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    confidence: float = 1.0
    source_type: str = "live_stream"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraGraphNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    camera_id: str
    name: str = ""
    latitude: float
    longitude: float
    heading_degrees: float = 0.0
    fov_degrees: float = 75.0
    coverage_radius_meters: float = 80.0
    region: str | None = None


class CameraGraphEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_camera_id: str
    to_camera_id: str
    distance_meters: float
    estimated_walk_seconds: float
    estimated_run_seconds: float
    estimated_vehicle_seconds: float
    transition_score: float = 0.5
    fov_overlap: bool = False
    geofence_penalty: float = 0.0


class PathConfidenceBreakdown(BaseModel):
    model_config = ConfigDict(extra="ignore")

    time_consistency: float = 0.5
    geo_distance: float = 0.5
    identity_similarity: float | None = None
    camera_fov: float | None = None
    event_severity: float | None = None
    travel_feasibility: float = 0.5


class PathHypothesisStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_index: int
    camera_id: str
    camera_name: str = ""
    latitude: float | None = None
    longitude: float | None = None
    timestamp: str
    event_id: str | None = None
    observation_id: str | None = None
    step_confidence: float = 0.5
    travel_mode: HypothesisStepMode = "unknown"
    travel_seconds_from_prev: float | None = None
    low_confidence_transition: bool = False


class PathHypothesis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hypothesis_id: str
    case_id: str | None = None
    subject_ref: InvestigationSubjectRef
    start_event_id: str | None = None
    steps: list[PathHypothesisStep] = Field(default_factory=list)
    confidence: float = 0.0
    confidence_breakdown: PathConfidenceBreakdown = Field(default_factory=PathConfidenceBreakdown)
    review_status: ReviewStatus = "pending"
    operator_review_required: bool = True
    safe_summary: str = "Possible movement path requiring operator review."
    created_at: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PathReconstructionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str | None = None
    event_id: str | None = None
    subject_ref: InvestigationSubjectRef | None = None
    backward_minutes: int = 20
    forward_minutes: int = 30
    max_candidates: int = 5
    camera_ids: list[str] | None = None


class PathReconstructionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: str
    status: Literal["ok", "insufficient_data", "no_access", "error"] = "ok"
    hypotheses: list[PathHypothesis] = Field(default_factory=list)
    evidence_ref_count: int = 0
    message: str = ""
    operator_review_required: bool = True


class HypothesisReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    review_status: ReviewStatus
    reviewer_notes: str | None = None


class HypothesisReviewRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hypothesis_id: str
    review_status: ReviewStatus
    reviewed_by: str
    reviewed_at: str
    reviewer_notes: str | None = None


class InvestigationTimelineEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entry_id: str
    case_id: str
    hypothesis_id: str | None = None
    event_type: str
    summary: str
    timestamp: str
    evidence_refs: list[str] = Field(default_factory=list)
    operator_review_required: bool = True


class InvestigationTimeline(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str
    entries: list[InvestigationTimelineEntry] = Field(default_factory=list)
    total_hypotheses: int = 0
    accepted: int = 0
    rejected: int = 0
    inconclusive: int = 0
    pending: int = 0
