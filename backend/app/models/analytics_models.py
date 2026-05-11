from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class AnalyticsTimeRange(AnalyticsBaseModel):
    start: str
    end: str
    bucket: str = "1h"


class AnalyticsBucket(AnalyticsBaseModel):
    key: str
    label: str
    start: str
    end: str


class EventTimeseriesPoint(AnalyticsBaseModel):
    bucket_start: str
    bucket_end: str
    total_events: int = 0
    critical_events: int = 0
    high_events: int = 0
    possible_incidents: int = 0
    avg_confidence: float = 0.0


class EventTypeBreakdown(AnalyticsBaseModel):
    event_type: str
    count: int = 0
    critical_count: int = 0
    avg_confidence: float = 0.0
    last_seen: str | None = None


class CaseTimeseriesPoint(AnalyticsBaseModel):
    bucket_start: str
    bucket_end: str
    opened_cases: int = 0
    resolved_cases: int = 0
    dismissed_cases: int = 0
    archived_cases: int = 0


class RiskHeatmapCell(AnalyticsBaseModel):
    camera_id: str
    risk_score: float = 0.0
    review_priority: str = "low"
    critical_event_count: int = 0
    open_case_count: int = 0
    requires_review_count: int = 0
    stream_status: str = "unknown"
    last_event_time: str | None = None


class CameraRiskSummary(AnalyticsBaseModel):
    camera_id: str
    risk_score: float = 0.0
    review_priority: str = "low"
    total_event_count: int = 0
    critical_event_count: int = 0
    open_case_count: int = 0
    unresolved_case_count: int = 0
    anomaly_event_count: int = 0
    identity_review_count: int = 0
    repeated_event_count: int = 0
    stream_status: str = "unknown"
    last_event_time: str | None = None


class ModelPerformanceSummary(AnalyticsBaseModel):
    model_key: str
    display_name: str
    status: str = "unknown"
    avg_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    avg_confidence: float | None = None
    event_count: int = 0
    benchmark_metrics: dict[str, Any] = Field(default_factory=dict)
    source: str = "runtime"


class AnomalyTrendSummary(AnalyticsBaseModel):
    total_anomalies: int = 0
    critical_anomalies: int = 0
    avg_score: float = 0.0
    max_score: float = 0.0
    false_positive_feedback_total: int = 0
    timeseries: list[EventTimeseriesPoint] = Field(default_factory=list)


class CaseAnalyticsSummary(AnalyticsBaseModel):
    total_cases: int = 0
    open_cases: int = 0
    investigating_cases: int = 0
    resolved_cases: int = 0
    dismissed_cases: int = 0
    archived_cases: int = 0
    cases_requiring_review: int = 0
    avg_resolution_hours: float | None = None
    evidence_items_total: int = 0
    notes_added_total: int = 0


class OperatorWorkloadSummary(AnalyticsBaseModel):
    operator_id: str
    assigned_cases: int = 0
    open_assigned_cases: int = 0
    cases_closed: int = 0
    notes_added: int = 0
    average_active_cases: float = 0.0
    review_backlog: int = 0
    audit_actions: int = 0


class StreamReliabilitySummary(AnalyticsBaseModel):
    camera_id: str
    stream_status: str = "unknown"
    fps_decode: float = 0.0
    fps_processed: float = 0.0
    dropped_frames_total: int = 0
    reconnect_attempts: int = 0
    offline_transitions: int = 0
    preview_clients: int = 0
    hls_available: bool = False
    webrtc_enabled: bool = False
    mjpeg_available: bool = False
    last_frame_at: str | None = None


class SystemPerformanceSummary(AnalyticsBaseModel):
    status: str = "unknown"
    gpu_status: str = "unknown"
    gpu_name: str | None = None
    avg_inference_latency_ms: float | None = None
    stream_processing_latency_ms: float | None = None
    queue_depth: int = 0
    active_streams: int = 0
    model_states: dict[str, Any] = Field(default_factory=dict)
    event_bus_health: dict[str, Any] = Field(default_factory=dict)
    runtime_checks: dict[str, Any] = Field(default_factory=dict)
    latency_percentiles: dict[str, float | None] = Field(default_factory=dict)
    persistence: dict[str, Any] = Field(default_factory=dict)
    retention: dict[str, Any] = Field(default_factory=dict)
    last_backup_at: str | None = None
    readiness_failures: list[str] = Field(default_factory=list)


class IdentityAnalyticsSummary(AnalyticsBaseModel):
    total_identities: int = 0
    active_identities: int = 0
    possible_matches: int = 0
    review_required_matches: int = 0
    cameras_with_identity_activity: int = 0
    recent_matches: list[dict[str, Any]] = Field(default_factory=list)


class OpenVocabAnalyticsSummary(AnalyticsBaseModel):
    total_scans: int = 0
    threat_hits: int = 0
    avg_risk_score: float = 0.0
    prompts_active: int = 0
    recent_results: list[dict[str, Any]] = Field(default_factory=list)


class AnalyticsExportRequest(AnalyticsBaseModel):
    format: str = "json"
    sections: list[str] = Field(default_factory=list)
    time_range: AnalyticsTimeRange
    filters: dict[str, Any] = Field(default_factory=dict)


class AnalyticsExportResponse(AnalyticsBaseModel):
    export_id: str
    format: str
    filename: str
    content_type: str
    generated_at: str
    status: str = "ready"
    content: str


class DashboardSummary(AnalyticsBaseModel):
    total_events: int = 0
    critical_events: int = 0
    open_cases: int = 0
    cases_requiring_review: int = 0
    active_streams: int = 0
    degraded_streams: int = 0
    avg_model_latency_ms: float = 0.0


class DashboardRisk(AnalyticsBaseModel):
    highest_risk_camera: str | None = None
    highest_risk_score: float = 0.0


class DashboardOverview(AnalyticsBaseModel):
    time_range: AnalyticsTimeRange
    summary: DashboardSummary
    risk: DashboardRisk
    source_status: dict[str, str] = Field(default_factory=dict)


class AnalyticsHealthReport(AnalyticsBaseModel):
    enabled: bool = False
    status: str = "disabled"
    storage: str = "jsonl"
    sources: dict[str, str] = Field(default_factory=dict)
    last_error: str | None = None
