from __future__ import annotations

import csv
import io
import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.analytics_models import (
    AnalyticsExportRequest,
    AnalyticsExportResponse,
    AnalyticsHealthReport,
    AnalyticsTimeRange,
    AnomalyTrendSummary,
    CameraRiskSummary,
    CaseAnalyticsSummary,
    CaseTimeseriesPoint,
    DashboardOverview,
    DashboardRisk,
    DashboardSummary,
    EventTimeseriesPoint,
    IdentityAnalyticsSummary,
    ModelPerformanceSummary,
    OpenVocabAnalyticsSummary,
    OperatorWorkloadSummary,
    RiskHeatmapCell,
    StreamReliabilitySummary,
    SystemPerformanceSummary,
)
from app.repositories.analytics_repository import AnalyticsRepository, load_analytics_config

BUCKET_SECONDS = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "1d": 24 * 60 * 60,
}
SEVERITY_ORDER = {"low": 1, "medium": 3, "high": 7, "critical": 12}
OPEN_CASE_STATUSES = {"open", "investigating"}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _safe_average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _safe_max(values: list[float]) -> float:
    return round(max(values), 4) if values else 0.0


def _bucket_duration(bucket: str) -> timedelta:
    return timedelta(seconds=BUCKET_SECONDS.get(bucket, BUCKET_SECONDS["1h"]))


def _uploaded_video_replay_counts() -> dict[str, int]:
    """Best-effort counts from persisted uploaded-video sessions (bounded scan)."""
    clips = 0
    with_clip = 0
    without = 0
    try:
        from app.services.uploaded_video_service import get_uploaded_video_service

        service = get_uploaded_video_service()
        for session in service.list_sessions()[:100]:
            for event in service.get_events(session.session_id):
                if event.replay_clip and getattr(event.replay_clip, "hash_sha256", None):
                    clips += 1
                    with_clip += 1
                else:
                    without += 1
    except Exception:
        return {"uploaded_video_replay_clips_generated_total": 0, "uploaded_video_events_with_clips": 0, "uploaded_video_events_without_clips": 0}
    return {
        "uploaded_video_replay_clips_generated_total": clips,
        "uploaded_video_events_with_clips": with_clip,
        "uploaded_video_events_without_clips": without,
    }


def _uploaded_video_intelligence_counts() -> dict[str, int | float]:
    try:
        from app.services.command_center_intelligence_service import get_command_center_intelligence_service

        summary = get_command_center_intelligence_service().analytics_summary()
    except Exception:
        return {
            "uploaded_video_processed_videos": 0,
            "uploaded_video_detection_count": 0,
            "uploaded_video_alerts_generated": 0,
            "uploaded_video_high_severity_detections": 0,
            "uploaded_video_average_confidence": 0.0,
            "uploaded_video_evidence_artifacts_created": 0,
        }
    return {
        "uploaded_video_processed_videos": int(summary.get("processed_videos") or 0),
        "uploaded_video_detection_count": int(summary.get("detections_total") or 0),
        "uploaded_video_alerts_generated": int(summary.get("alerts_generated") or 0),
        "uploaded_video_high_severity_detections": int(summary.get("high_severity_detections") or 0),
        "uploaded_video_average_confidence": float(summary.get("average_confidence") or 0.0),
        "uploaded_video_evidence_artifacts_created": int(summary.get("evidence_artifacts_created") or 0),
    }


def _drone_mission_analytics_counts() -> dict[str, int]:
    """Best-effort drone patrol mission stats from the JSONL repository."""
    try:
        from app.repositories.drone_mission_repository import get_drone_mission_repository
        from app.models.drone_mission_models import DroneMissionStatus

        repo = get_drone_mission_repository()
        missions = repo.list_missions(limit=500)
        today_count = 0
        active_count = 0
        failure_count = 0
        observation_count = 0
        today_str = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).date().isoformat()
        for m in missions:
            created = str(m.created_at or "")
            if created.startswith(today_str):
                today_count += 1
            if m.status == DroneMissionStatus.EXECUTING:
                active_count += 1
            if m.status == DroneMissionStatus.FAILED:
                failure_count += 1
        # Count telemetry observations across all sessions
        sessions = repo.list_sessions(limit=200)
        for s in sessions:
            observation_count += s.telemetry_count
        return {
            "drone_missions_today": today_count,
            "active_simulated_patrols": active_count,
            "drone_observations": observation_count,
            "mission_failures": failure_count,
        }
    except Exception:
        return {
            "drone_missions_today": 0,
            "active_simulated_patrols": 0,
            "drone_observations": 0,
            "mission_failures": 0,
        }


def _bucket_windows(start: datetime, end: datetime, bucket: str) -> list[tuple[datetime, datetime]]:
    delta = _bucket_duration(bucket)
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        nxt = min(cursor + delta, end)
        windows.append((cursor, nxt))
        cursor = nxt
    if not windows:
        windows.append((start, end))
    return windows


def _first_camera_id(payload: dict[str, Any]) -> str | None:
    if payload.get("camera_id"):
        return str(payload["camera_id"])
    camera_ids = payload.get("camera_ids") or []
    if isinstance(camera_ids, list) and camera_ids:
        return str(camera_ids[0])
    return None


def _camera_ids(payload: dict[str, Any]) -> list[str]:
    values = payload.get("camera_ids") or []
    if values:
        return [str(item) for item in values if item]
    first = _first_camera_id(payload)
    return [first] if first else []


def _severity_weight(severity: str, weights: dict[str, int]) -> int:
    return int(weights.get(str(severity or "").lower(), SEVERITY_ORDER.get(str(severity or "").lower(), 0)))


def _review_priority(score: float) -> str:
    if score >= 60:
        return "critical"
    if score >= 30:
        return "high"
    if score >= 12:
        return "medium"
    return "low"


class AnalyticsService:
    def __init__(
        self,
        repository: AnalyticsRepository | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._raw_config = config or load_analytics_config()
        self._config = dict(self._raw_config.get("analytics") or {})
        self._repository = repository or AnalyticsRepository(config=self._raw_config)
        self._cache_enabled = bool((self._config.get("cache") or {}).get("enabled", True))
        self._cache_ttl_seconds = int((self._config.get("cache") or {}).get("ttl_seconds", 30))
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    @property
    def repository(self) -> AnalyticsRepository:
        return self._repository

    def get_dashboard_overview(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> DashboardOverview:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> DashboardOverview:
            events = self.repository.get_events(normalized, filters)
            cases = self.repository.get_cases(normalized, filters)
            camera_risk = self._compute_camera_risk(events, cases, self.repository.get_stream_health(normalized, filters), self.repository.get_identity_matches(normalized, filters))
            model_performance = self.get_model_performance(normalized, filters)
            replay_counts = _uploaded_video_replay_counts()
            intelligence_counts = _uploaded_video_intelligence_counts()
            summary = DashboardSummary(
                total_events=len(events),
                critical_events=sum(1 for item in events if str(item.get("severity") or "").lower() == "critical"),
                open_cases=sum(1 for item in cases if str(item.get("status") or "").lower() in OPEN_CASE_STATUSES),
                cases_requiring_review=sum(1 for item in cases if bool(item.get("requires_review"))),
                active_streams=sum(1 for item in self.repository.get_stream_health(normalized, filters) if str(item.get("state") or "").lower() == "running"),
                degraded_streams=sum(
                    1
                    for item in self.repository.get_stream_health(normalized, filters)
                    if str((item.get("health") or {}).get("status") or "").lower() in {"degraded", "reconnecting", "failed"}
                ),
                avg_model_latency_ms=round(
                    _safe_average([float(item.avg_latency_ms) for item in model_performance if item.avg_latency_ms is not None]),
                    2,
                ) if model_performance else 0.0,
                uploaded_video_replay_clips_generated_total=int(replay_counts.get("uploaded_video_replay_clips_generated_total", 0)),
                uploaded_video_events_with_clips=int(replay_counts.get("uploaded_video_events_with_clips", 0)),
                uploaded_video_events_without_clips=int(replay_counts.get("uploaded_video_events_without_clips", 0)),
                uploaded_video_processed_videos=int(intelligence_counts.get("uploaded_video_processed_videos", 0)),
                uploaded_video_detection_count=int(intelligence_counts.get("uploaded_video_detection_count", 0)),
                uploaded_video_alerts_generated=int(intelligence_counts.get("uploaded_video_alerts_generated", 0)),
                uploaded_video_high_severity_detections=int(intelligence_counts.get("uploaded_video_high_severity_detections", 0)),
                uploaded_video_average_confidence=float(intelligence_counts.get("uploaded_video_average_confidence", 0.0)),
                uploaded_video_evidence_artifacts_created=int(intelligence_counts.get("uploaded_video_evidence_artifacts_created", 0)),
                **_drone_mission_analytics_counts(),
            )
            top_risk = camera_risk[0] if camera_risk else None
            return DashboardOverview(
                time_range=normalized,
                summary=summary,
                risk=DashboardRisk(
                    highest_risk_camera=top_risk.camera_id if top_risk else None,
                    highest_risk_score=top_risk.risk_score if top_risk else 0.0,
                ),
                source_status=self.repository.get_source_statuses(),
            )

        return self._with_cache("overview", normalized, filters, _compute)

    def get_event_timeseries(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, bucket: str | None = None, filters: dict[str, Any] | None = None) -> list[EventTimeseriesPoint]:
        normalized = self._normalize_time_range(time_range, bucket=bucket)
        filters = filters or {}

        def _compute() -> list[EventTimeseriesPoint]:
            events = self.repository.get_events(normalized, filters)
            windows = _bucket_windows(_parse_datetime(normalized.start) or _now_utc(), _parse_datetime(normalized.end) or _now_utc(), normalized.bucket)
            return self._aggregate_event_points(events, windows)

        return self._with_cache("event_timeseries", normalized, filters, _compute)

    def get_events_by_type(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> list[dict[str, Any]]:
            items: dict[str, list[dict[str, Any]]] = {}
            for event in self.repository.get_events(normalized, filters):
                items.setdefault(str(event.get("event_type") or "event"), []).append(event)
            rows = []
            for event_type, group in items.items():
                confidences = [float(item.get("confidence") or 0.0) for item in group if item.get("confidence") is not None]
                rows.append(
                    {
                        "event_type": event_type,
                        "count": len(group),
                        "critical_count": sum(1 for item in group if str(item.get("severity") or "").lower() == "critical"),
                        "avg_confidence": _safe_average(confidences) if confidences else 0.0,
                        "last_seen": max((str(item.get("timestamp") or "") for item in group), default=None),
                    }
                )
            rows.sort(key=lambda item: item["count"], reverse=True)
            return rows

        return self._with_cache("events_by_type", normalized, filters, _compute)

    def get_case_summary(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> CaseAnalyticsSummary:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> CaseAnalyticsSummary:
            cases = self.repository.get_cases(normalized, filters)
            evidence = self.repository.get_evidence(normalized, filters)
            notes = self.repository.get_case_notes(normalized, filters)
            resolution_hours = []
            for case in cases:
                created = _parse_datetime(case.get("created_at"))
                closed = _parse_datetime(case.get("closed_at"))
                if created is not None and closed is not None:
                    resolution_hours.append((closed - created).total_seconds() / 3600.0)
            return CaseAnalyticsSummary(
                total_cases=len(cases),
                open_cases=sum(1 for item in cases if str(item.get("status") or "").lower() == "open"),
                investigating_cases=sum(1 for item in cases if str(item.get("status") or "").lower() == "investigating"),
                resolved_cases=sum(1 for item in cases if str(item.get("status") or "").lower() == "resolved"),
                dismissed_cases=sum(1 for item in cases if str(item.get("status") or "").lower() == "dismissed"),
                archived_cases=sum(1 for item in cases if str(item.get("status") or "").lower() == "archived"),
                cases_requiring_review=sum(1 for item in cases if bool(item.get("requires_review"))),
                avg_resolution_hours=round(_safe_average(resolution_hours), 2) if resolution_hours else None,
                evidence_items_total=len(evidence),
                notes_added_total=len(notes),
            )

        return self._with_cache("case_summary", normalized, filters, _compute)

    def get_case_timeseries(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, bucket: str | None = None, filters: dict[str, Any] | None = None) -> list[CaseTimeseriesPoint]:
        normalized = self._normalize_time_range(time_range, bucket=bucket)
        filters = filters or {}

        def _compute() -> list[CaseTimeseriesPoint]:
            cases = self.repository.get_cases(normalized, filters)
            windows = _bucket_windows(_parse_datetime(normalized.start) or _now_utc(), _parse_datetime(normalized.end) or _now_utc(), normalized.bucket)
            points: list[CaseTimeseriesPoint] = []
            for bucket_start, bucket_end in windows:
                opened = 0
                resolved = 0
                dismissed = 0
                archived = 0
                for case in cases:
                    created_at = _parse_datetime(case.get("created_at"))
                    closed_at = _parse_datetime(case.get("closed_at"))
                    if created_at is not None and bucket_start <= created_at < bucket_end:
                        opened += 1
                    if closed_at is not None and bucket_start <= closed_at < bucket_end:
                        status = str(case.get("status") or "").lower()
                        if status == "resolved":
                            resolved += 1
                        elif status == "dismissed":
                            dismissed += 1
                        elif status == "archived":
                            archived += 1
                points.append(
                    CaseTimeseriesPoint(
                        bucket_start=_iso(bucket_start),
                        bucket_end=_iso(bucket_end),
                        opened_cases=opened,
                        resolved_cases=resolved,
                        dismissed_cases=dismissed,
                        archived_cases=archived,
                    )
                )
            return points

        return self._with_cache("case_timeseries", normalized, filters, _compute)

    def get_camera_risk(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> list[CameraRiskSummary]:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> list[CameraRiskSummary]:
            return self._compute_camera_risk(
                self.repository.get_events(normalized, filters),
                self.repository.get_cases(normalized, filters),
                self.repository.get_stream_health(normalized, filters),
                self.repository.get_identity_matches(normalized, filters),
            )

        return self._with_cache("camera_risk", normalized, filters, _compute)

    def get_camera_risk_heatmap(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> list[RiskHeatmapCell]:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> list[RiskHeatmapCell]:
            return [
                RiskHeatmapCell(
                    camera_id=item.camera_id,
                    risk_score=item.risk_score,
                    review_priority=item.review_priority,
                    critical_event_count=item.critical_event_count,
                    open_case_count=item.open_case_count,
                    requires_review_count=item.unresolved_case_count,
                    stream_status=item.stream_status,
                    last_event_time=item.last_event_time,
                )
                for item in self.get_camera_risk(normalized, filters)
            ]

        return self._with_cache("camera_heatmap", normalized, filters, _compute)

    def get_model_performance(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> list[ModelPerformanceSummary]:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> list[ModelPerformanceSummary]:
            rows = [
                ModelPerformanceSummary.model_validate(item)
                for item in self.repository.get_model_metrics(normalized, filters)
            ]
            return rows

        return self._with_cache("model_performance", normalized, filters, _compute)

    def get_anomaly_trends(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> AnomalyTrendSummary:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> AnomalyTrendSummary:
            anomaly_events = [
                item
                for item in self.repository.get_events(normalized, filters)
                if "anomaly" in str(item.get("event_type") or "").lower()
            ]
            system_metrics = self.repository.get_system_metrics().get("metrics", {})
            windows = _bucket_windows(_parse_datetime(normalized.start) or _now_utc(), _parse_datetime(normalized.end) or _now_utc(), normalized.bucket)
            timeseries = self._aggregate_event_points(anomaly_events, windows)
            scores = [float(item.get("risk_score") or item.get("confidence") or 0.0) for item in anomaly_events]
            return AnomalyTrendSummary(
                total_anomalies=len(anomaly_events),
                critical_anomalies=sum(1 for item in anomaly_events if str(item.get("severity") or "").lower() == "critical"),
                avg_score=_safe_average(scores),
                max_score=_safe_max(scores),
                false_positive_feedback_total=int(system_metrics.get("anomaly_false_alarm_feedback_total") or 0),
                timeseries=timeseries,
            )

        return self._with_cache("anomaly_trends", normalized, filters, _compute)

    def get_identity_summary(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> IdentityAnalyticsSummary:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> IdentityAnalyticsSummary:
            profiles = self.repository.get_identity_profiles(filters)
            matches = self.repository.get_identity_matches(normalized, filters)
            records = self.repository.get_global_identity_records(filters)
            recent_matches = sorted(matches, key=lambda item: float(item.get("matched_at") or 0.0), reverse=True)[:10]
            active_identities = sum(1 for item in records if str(item.get("status") or "").lower() == "active")
            cameras = {str(item.get("camera_id")) for item in matches if item.get("camera_id")}
            return IdentityAnalyticsSummary(
                total_identities=max(len(profiles), len(records)),
                active_identities=active_identities,
                possible_matches=len(matches),
                review_required_matches=sum(1 for item in matches if bool(item.get("operator_review_required", True))),
                cameras_with_identity_activity=len(cameras),
                recent_matches=recent_matches,
            )

        return self._with_cache("identity_summary", normalized, filters, _compute)

    def get_open_vocab_summary(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> OpenVocabAnalyticsSummary:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> OpenVocabAnalyticsSummary:
            results = self.repository.get_open_vocab_results(normalized, filters)
            system_metrics = self.repository.get_system_metrics().get("metrics", {})
            scores = [float(item.get("risk_score") or 0.0) for item in results]
            threat_hits = sum(1 for item in results if (item.get("detections") or []))
            return OpenVocabAnalyticsSummary(
                total_scans=len(results),
                threat_hits=threat_hits,
                avg_risk_score=_safe_average(scores),
                prompts_active=int(system_metrics.get("open_vocab_prompts_active") or 0),
                recent_results=results[:10],
            )

        return self._with_cache("open_vocab_summary", normalized, filters, _compute)

    def get_stream_reliability(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> list[StreamReliabilitySummary]:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> list[StreamReliabilitySummary]:
            stream_items = self.repository.get_stream_health(normalized, filters)
            summaries: list[StreamReliabilitySummary] = []
            from app.services.hls_service import get_hls_service
            from app.services.webrtc_service import get_webrtc_service

            hls_service = get_hls_service()
            webrtc_service = get_webrtc_service()
            for item in stream_items:
                health = dict(item.get("health") or {})
                stats = dict(item.get("stats") or {})
                camera_id = str(item.get("camera_id") or "")
                summaries.append(
                    StreamReliabilitySummary(
                        camera_id=camera_id,
                        stream_status=str(health.get("status") or item.get("state") or "unknown"),
                        fps_decode=float(stats.get("fps_decode") or health.get("fps_decode") or 0.0),
                        fps_processed=float(stats.get("fps_processed") or health.get("fps_processed") or 0.0),
                        dropped_frames_total=int(stats.get("dropped_frames_total") or health.get("dropped_frames_total") or 0),
                        reconnect_attempts=int(stats.get("reconnect_attempts") or health.get("reconnect_attempts") or 0),
                        offline_transitions=int(stats.get("offline_transitions") or 0),
                        preview_clients=int(stats.get("preview_clients_active") or 0),
                        hls_available=bool(hls_service.get_playlist_info(camera_id).available),
                        webrtc_enabled=bool(webrtc_service.get_status(camera_id).get("enabled")),
                        mjpeg_available=bool(item.get("stream_id")),
                        last_frame_at=stats.get("last_frame_at") or health.get("last_frame_at"),
                    )
                )
            return summaries

        return self._with_cache("stream_reliability", normalized, filters, _compute)

    def get_operator_workload(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> list[OperatorWorkloadSummary]:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> list[OperatorWorkloadSummary]:
            cases = self.repository.get_cases(normalized, filters)
            audit_logs = self.repository.get_audit_activity(normalized, filters)
            case_audits = self.repository.get_case_audit_logs(normalized, filters)
            operators: dict[str, dict[str, Any]] = {}

            def ensure(operator_id: str) -> dict[str, Any]:
                payload = operators.setdefault(
                    operator_id,
                    {
                        "assigned_cases": 0,
                        "open_assigned_cases": 0,
                        "cases_closed": 0,
                        "notes_added": 0,
                        "review_backlog": 0,
                        "audit_actions": 0,
                    },
                )
                return payload

            for case in cases:
                assigned_to = str(case.get("assigned_to") or "").strip()
                if not assigned_to:
                    continue
                payload = ensure(assigned_to)
                payload["assigned_cases"] += 1
                if str(case.get("status") or "").lower() in OPEN_CASE_STATUSES:
                    payload["open_assigned_cases"] += 1
                if bool(case.get("requires_review")) and str(case.get("status") or "").lower() in OPEN_CASE_STATUSES:
                    payload["review_backlog"] += 1

            for item in audit_logs:
                username = str(item.get("username") or item.get("user_id") or "").strip()
                if not username:
                    continue
                payload = ensure(username)
                payload["audit_actions"] += 1
                action = str(item.get("action") or "").lower()
                if action == "case_closed":
                    payload["cases_closed"] += 1
                if action == "case_note_added":
                    payload["notes_added"] += 1

            for item in case_audits:
                actor = str(item.get("actor") or "").strip()
                if not actor:
                    continue
                payload = ensure(actor)
                action = str(item.get("action") or "").lower()
                if action == "status_changed" and str(item.get("detail") or "").lower().startswith("case status changed to resolved"):
                    payload["cases_closed"] += 1
                if action == "note_added":
                    payload["notes_added"] += 1

            rows = [
                OperatorWorkloadSummary(
                    operator_id=operator_id,
                    assigned_cases=payload["assigned_cases"],
                    open_assigned_cases=payload["open_assigned_cases"],
                    cases_closed=payload["cases_closed"],
                    notes_added=payload["notes_added"],
                    average_active_cases=float(payload["open_assigned_cases"]),
                    review_backlog=payload["review_backlog"],
                    audit_actions=payload["audit_actions"],
                )
                for operator_id, payload in operators.items()
            ]
            rows.sort(key=lambda item: (item.review_backlog, item.open_assigned_cases, item.audit_actions), reverse=True)
            return rows

        return self._with_cache("operator_workload", normalized, filters, _compute)

    def get_system_performance(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, filters: dict[str, Any] | None = None) -> SystemPerformanceSummary:
        normalized = self._normalize_time_range(time_range)
        filters = filters or {}

        def _compute() -> SystemPerformanceSummary:
            del filters
            payload = self.repository.get_system_metrics()
            metrics = payload.get("metrics") or {}
            system = payload.get("system") or {}
            event_bus = payload.get("event_bus") or {}
            streaming = (payload.get("streaming") or {}).get("streaming") or {}
            persistence = {}
            readiness_failures: list[str] = []
            gpu_status = "healthy"
            gpu_name = None
            try:
                import torch

                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
                else:
                    gpu_status = "degraded"
            except Exception:
                gpu_status = "unknown"
            try:
                from app.services.runtime_health_service import get_runtime_health_service

                runtime_health = get_runtime_health_service()
                persistence = dict(runtime_health.get_health(include_sensitive=False).get("persistence") or {})
                readiness_failures = list(runtime_health.is_ready().get("failures") or [])
            except Exception:
                persistence = {}
                readiness_failures = []
            status = "healthy" if gpu_status == "healthy" else gpu_status
            if persistence.get("status") == "failed":
                status = "failed"
            elif persistence.get("status") == "degraded" and status == "healthy":
                status = "degraded"
            return SystemPerformanceSummary(
                status=status,
                gpu_status=gpu_status,
                gpu_name=gpu_name,
                avg_inference_latency_ms=metrics.get("avg_inference_time_ms"),
                stream_processing_latency_ms=metrics.get("stream_processing_latency_ms"),
                queue_depth=int(metrics.get("stream_queue_depth") or 0),
                active_streams=int(streaming.get("active_streams") or metrics.get("active_streams") or 0),
                model_states=dict(system.get("model_health_status") or system.get("model_status") or {}),
                event_bus_health=dict(event_bus),
                runtime_checks=dict(streaming),
                latency_percentiles={
                    "p50_ms": None,
                    "p95_ms": None,
                    "p99_ms": None,
                },
                persistence=persistence,
                retention={
                    "mode": persistence.get("retention_mode"),
                },
                last_backup_at=persistence.get("last_backup_at"),
                readiness_failures=readiness_failures,
            )

        return self._with_cache("system_performance", normalized, filters, _compute)

    def export_analytics(self, export_request: AnalyticsExportRequest | dict[str, Any]) -> AnalyticsExportResponse:
        request = export_request if isinstance(export_request, AnalyticsExportRequest) else AnalyticsExportRequest.model_validate(export_request)
        sections = request.sections or [
            "overview",
            "event_timeseries",
            "case_summary",
            "camera_risk",
            "model_performance",
            "anomaly_trends",
            "stream_reliability",
            "operator_workload",
            "system_performance",
            "identity_summary",
            "open_vocab_summary",
        ]
        dataset = self._build_export_payload(request.time_range, request.filters, sections)
        export_id = f"analytics_{uuid.uuid4().hex[:12]}"
        generated_at = _iso(_now_utc())
        if str(request.format).lower() == "csv":
            content = self._render_csv(dataset)
            content_type = "text/csv"
            filename = f"{export_id}.csv"
        else:
            content = json.dumps(dataset, indent=2)
            content_type = "application/json"
            filename = f"{export_id}.json"
        self._increment_metric("analytics_exports_total")
        return AnalyticsExportResponse(
            export_id=export_id,
            format=str(request.format).lower(),
            filename=filename,
            content_type=content_type,
            generated_at=generated_at,
            content=content,
        )

    def get_health(self) -> AnalyticsHealthReport:
        statuses = self.repository.probe_sources()
        enabled = self.repository.enabled
        if not enabled:
            status = "disabled"
        else:
            missing = [name for name, value in statuses.items() if value in {"missing", "failed", "error"}]
            degraded = [name for name, value in statuses.items() if value in {"degraded", "missing"}]
            if self._is_production() and missing and bool((self._config.get("production") or {}).get("fail_if_required_storage_missing", True)):
                status = "failed"
            elif degraded:
                status = "degraded"
            else:
                status = "healthy"
        return AnalyticsHealthReport(
            enabled=enabled,
            status=status,
            storage=self.repository.storage_backend,
            sources=statuses,
            last_error=self.repository.get_last_error(),
        )

    def _normalize_time_range(self, time_range: AnalyticsTimeRange | dict[str, Any] | None, bucket: str | None = None) -> AnalyticsTimeRange:
        aggregation_cfg = dict(self._config.get("aggregation") or {})
        default_hours = int(aggregation_cfg.get("default_window_hours", 24))
        max_window_days = int(aggregation_cfg.get("max_window_days", 90))
        default_bucket = str(bucket or aggregation_cfg.get("default_bucket") or "1h")
        if default_bucket not in BUCKET_SECONDS:
            default_bucket = "1h"

        if time_range is None:
            end = _now_utc()
            start = end - timedelta(hours=default_hours)
            return AnalyticsTimeRange(start=_iso(start), end=_iso(end), bucket=default_bucket)

        payload = time_range if isinstance(time_range, AnalyticsTimeRange) else AnalyticsTimeRange.model_validate(time_range)
        start = _parse_datetime(payload.start) or (_now_utc() - timedelta(hours=default_hours))
        end = _parse_datetime(payload.end) or _now_utc()
        if end < start:
            start, end = end, start
        max_start = end - timedelta(days=max_window_days)
        if start < max_start:
            start = max_start
        return AnalyticsTimeRange(start=_iso(start), end=_iso(end), bucket=bucket or payload.bucket or default_bucket)

    def _aggregate_event_points(self, events: list[dict[str, Any]], windows: list[tuple[datetime, datetime]]) -> list[EventTimeseriesPoint]:
        points: list[EventTimeseriesPoint] = []
        for bucket_start, bucket_end in windows:
            group = [
                item
                for item in events
                if (event_at := _parse_datetime(item.get("timestamp"))) is not None and bucket_start <= event_at < bucket_end
            ]
            confidences = [float(item.get("confidence") or 0.0) for item in group if item.get("confidence") is not None]
            points.append(
                EventTimeseriesPoint(
                    bucket_start=_iso(bucket_start),
                    bucket_end=_iso(bucket_end),
                    total_events=len(group),
                    critical_events=sum(1 for item in group if str(item.get("severity") or "").lower() == "critical"),
                    high_events=sum(1 for item in group if str(item.get("severity") or "").lower() == "high"),
                    possible_incidents=sum(
                        1 for item in group if str(item.get("severity") or "").lower() in {"high", "critical"}
                    ),
                    avg_confidence=_safe_average(confidences),
                )
            )
        return points

    def _compute_camera_risk(
        self,
        events: list[dict[str, Any]],
        cases: list[dict[str, Any]],
        streams: list[dict[str, Any]],
        identity_matches: list[dict[str, Any]],
    ) -> list[CameraRiskSummary]:
        config = dict(self._config.get("risk_scoring") or {})
        weights = dict(config.get("severity_weights") or SEVERITY_ORDER)
        case_weight = float(config.get("case_weight", 5))
        unresolved_case_multiplier = float(config.get("unresolved_case_multiplier", 1.5))
        repeated_camera_multiplier = float(config.get("repeated_camera_multiplier", 1.2))

        cameras = {camera_id for item in events for camera_id in _camera_ids(item)}
        cameras.update({camera_id for item in cases for camera_id in _camera_ids(item)})
        cameras.update({str(item.get("camera_id")) for item in identity_matches if item.get("camera_id")})
        cameras.update({str(item.get("camera_id")) for item in streams if item.get("camera_id")})

        stream_map = {str(item.get("camera_id")): item for item in streams if item.get("camera_id")}
        summaries: list[CameraRiskSummary] = []
        for camera_id in sorted(cameras):
            camera_events = [item for item in events if camera_id in _camera_ids(item)]
            camera_cases = [item for item in cases if camera_id in _camera_ids(item)]
            camera_identity = [item for item in identity_matches if str(item.get("camera_id") or "") == camera_id]
            severity_weighted_events = sum(_severity_weight(str(item.get("severity") or ""), weights) for item in camera_events)
            critical_event_count = sum(1 for item in camera_events if str(item.get("severity") or "").lower() == "critical")
            open_case_count = sum(1 for item in camera_cases if str(item.get("status") or "").lower() in OPEN_CASE_STATUSES)
            unresolved_case_count = open_case_count
            anomaly_event_count = sum(1 for item in camera_events if "anomaly" in str(item.get("event_type") or "").lower())
            identity_review_count = sum(1 for item in camera_identity if bool(item.get("operator_review_required", True)))
            repeated_event_count = max(0, len(camera_events) - 1)

            base_score = severity_weighted_events
            base_score += open_case_count * case_weight
            base_score += anomaly_event_count * 2.0
            base_score += identity_review_count * 2.0
            if unresolved_case_count > 0:
                base_score *= unresolved_case_multiplier
            if repeated_event_count > 0:
                base_score *= repeated_camera_multiplier
            risk_score = round(base_score, 2)
            self._increment_metric("analytics_risk_score_computed_total")

            last_event_time = max((str(item.get("timestamp") or "") for item in camera_events), default=None)
            stream_payload = stream_map.get(camera_id) or {}
            stream_status = str((stream_payload.get("health") or {}).get("status") or stream_payload.get("state") or "unknown")
            summaries.append(
                CameraRiskSummary(
                    camera_id=camera_id,
                    risk_score=risk_score,
                    review_priority=_review_priority(risk_score),
                    total_event_count=len(camera_events),
                    critical_event_count=critical_event_count,
                    open_case_count=open_case_count,
                    unresolved_case_count=unresolved_case_count,
                    anomaly_event_count=anomaly_event_count,
                    identity_review_count=identity_review_count,
                    repeated_event_count=repeated_event_count,
                    stream_status=stream_status,
                    last_event_time=last_event_time,
                )
            )
        summaries.sort(key=lambda item: item.risk_score, reverse=True)
        return summaries

    def _build_export_payload(self, time_range: AnalyticsTimeRange, filters: dict[str, Any], sections: list[str]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "generated_at": _iso(_now_utc()),
            "time_range": time_range.model_dump(mode="json"),
            "filters": filters,
            "source_status": self.repository.get_source_statuses(),
        }
        for section in sections:
            if section == "overview":
                payload["overview"] = self.get_dashboard_overview(time_range, filters).model_dump(mode="json")
            elif section == "event_timeseries":
                payload["event_timeseries"] = [item.model_dump(mode="json") for item in self.get_event_timeseries(time_range, filters=filters)]
            elif section == "events_by_type":
                payload["events_by_type"] = self.get_events_by_type(time_range, filters)
            elif section == "case_summary":
                payload["case_summary"] = self.get_case_summary(time_range, filters).model_dump(mode="json")
            elif section == "case_timeseries":
                payload["case_timeseries"] = [item.model_dump(mode="json") for item in self.get_case_timeseries(time_range, filters=filters)]
            elif section == "camera_risk":
                payload["camera_risk"] = [item.model_dump(mode="json") for item in self.get_camera_risk(time_range, filters)]
            elif section == "model_performance":
                payload["model_performance"] = [item.model_dump(mode="json") for item in self.get_model_performance(time_range, filters)]
            elif section == "anomaly_trends":
                payload["anomaly_trends"] = self.get_anomaly_trends(time_range, filters).model_dump(mode="json")
            elif section == "stream_reliability":
                payload["stream_reliability"] = [item.model_dump(mode="json") for item in self.get_stream_reliability(time_range, filters)]
            elif section == "operator_workload":
                payload["operator_workload"] = [item.model_dump(mode="json") for item in self.get_operator_workload(time_range, filters)]
            elif section == "system_performance":
                payload["system_performance"] = self.get_system_performance(time_range, filters).model_dump(mode="json")
            elif section == "identity_summary":
                payload["identity_summary"] = self.get_identity_summary(time_range, filters).model_dump(mode="json")
            elif section == "open_vocab_summary":
                payload["open_vocab_summary"] = self.get_open_vocab_summary(time_range, filters).model_dump(mode="json")
        return payload

    def _render_csv(self, dataset: dict[str, Any]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["section", "field", "value"])
        for section, value in dataset.items():
            if isinstance(value, dict):
                for field, item in value.items():
                    writer.writerow([section, field, json.dumps(item) if isinstance(item, (dict, list)) else item])
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    writer.writerow([section, index, json.dumps(item)])
            else:
                writer.writerow([section, "", value])
        return buffer.getvalue()

    def _with_cache(self, name: str, time_range: AnalyticsTimeRange, filters: dict[str, Any], compute: Any):
        if not self._cache_enabled:
            return compute()
        key = json.dumps(
            {
                "name": name,
                "time_range": time_range.model_dump(mode="json"),
                "filters": filters,
            },
            sort_keys=True,
        )
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and entry[0] > now:
                self._increment_metric("analytics_cache_hits_total")
                return entry[1]
        self._increment_metric("analytics_cache_misses_total")
        value = compute()
        with self._lock:
            self._cache[key] = (now + self._cache_ttl_seconds, value)
        return value

    @staticmethod
    def _increment_metric(name: str, count: int = 1) -> None:
        try:
            from inference.monitoring.metrics import get_metrics as get_monitoring_metrics

            get_monitoring_metrics().increment(name, count)
        except Exception:
            pass
        try:
            from inference.metrics import metrics as core_metrics

            core_metrics.increment(name, count)
        except Exception:
            pass

    @staticmethod
    def _is_production() -> bool:
        return (str(__import__("os").environ.get("APP_ENV") or __import__("os").environ.get("AEGIS_ENV") or "development").strip().lower() in {"prod", "production"})


_analytics_service: AnalyticsService | None = None
_analytics_service_lock = threading.Lock()


def get_analytics_service() -> AnalyticsService:
    global _analytics_service
    if _analytics_service is None:
        with _analytics_service_lock:
            if _analytics_service is None:
                _analytics_service = AnalyticsService()
    return _analytics_service
