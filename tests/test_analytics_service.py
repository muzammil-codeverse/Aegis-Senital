from __future__ import annotations

from types import SimpleNamespace

from app.services.analytics_service import AnalyticsService


class _ServiceRepository:
    enabled = True
    storage_backend = "jsonl"

    def __init__(self, *, events=None, cases=None, evidence=None, notes=None, case_audits=None, streams=None, models=None, audits=None, identity_matches=None, identity_profiles=None, identity_records=None, open_vocab=None, system=None, statuses=None):
        self._events = events or []
        self._cases = cases or []
        self._evidence = evidence or []
        self._notes = notes or []
        self._case_audits = case_audits or []
        self._streams = streams or []
        self._models = models or []
        self._audits = audits or []
        self._identity_matches = identity_matches or []
        self._identity_profiles = identity_profiles or []
        self._identity_records = identity_records or []
        self._open_vocab = open_vocab or []
        self._system = system or {"metrics": {}, "system": {}, "event_bus": {}, "streaming": {"streaming": {}}}
        self._statuses = statuses or {
            "events": "healthy",
            "cases": "healthy",
            "streaming": "healthy",
            "model_metrics": "healthy",
            "system_health": "healthy",
        }

    def get_events(self, time_range, filters=None):
        del time_range, filters
        return list(self._events)

    def get_cases(self, time_range, filters=None):
        del time_range, filters
        return list(self._cases)

    def get_evidence(self, time_range, filters=None):
        del time_range, filters
        return list(self._evidence)

    def get_case_notes(self, time_range, filters=None):
        del time_range, filters
        return list(self._notes)

    def get_case_audit_logs(self, time_range, filters=None):
        del time_range, filters
        return list(self._case_audits)

    def get_stream_health(self, time_range, filters=None):
        del time_range, filters
        return list(self._streams)

    def get_model_metrics(self, time_range, filters=None):
        del time_range, filters
        return list(self._models)

    def get_audit_activity(self, time_range, filters=None):
        del time_range, filters
        return list(self._audits)

    def get_identity_profiles(self, filters=None):
        del filters
        return list(self._identity_profiles)

    def get_identity_matches(self, time_range, filters=None):
        del time_range, filters
        return list(self._identity_matches)

    def get_global_identity_records(self, filters=None):
        del filters
        return list(self._identity_records)

    def get_open_vocab_results(self, time_range, filters=None):
        del time_range, filters
        return list(self._open_vocab)

    def get_system_metrics(self):
        return dict(self._system)

    def get_source_statuses(self):
        return dict(self._statuses)

    def probe_sources(self):
        return dict(self._statuses)

    def get_last_error(self):
        return None


def _config():
    return {
        "analytics": {
            "enabled": True,
            "cache": {"enabled": False},
            "aggregation": {"default_window_hours": 24, "max_window_days": 90, "default_bucket": "1h"},
        }
    }


def test_analytics_service_returns_honest_zeroes_for_empty_data():
    service = AnalyticsService(repository=_ServiceRepository(), config=_config())

    overview = service.get_dashboard_overview(None, {})
    case_summary = service.get_case_summary(None, {})
    anomaly = service.get_anomaly_trends(None, {})

    assert overview.summary.total_events == 0
    assert overview.summary.open_cases == 0
    assert case_summary.total_cases == 0
    assert case_summary.avg_resolution_hours is None
    assert anomaly.total_anomalies == 0
    assert anomaly.avg_score == 0.0


def test_analytics_service_aggregates_timeseries_streams_workload_and_models(monkeypatch):
    repository = _ServiceRepository(
        events=[
            {
                "event_id": "evt-1",
                "event_type": "possible_incident",
                "timestamp": "2026-05-10T01:15:00+00:00",
                "severity": "critical",
                "confidence": 0.9,
                "camera_id": "cam_01",
                "camera_ids": ["cam_01"],
                "risk_score": 0.9,
            },
            {
                "event_id": "evt-2",
                "event_type": "anomaly_motion",
                "timestamp": "2026-05-10T02:10:00+00:00",
                "severity": "high",
                "confidence": 0.6,
                "camera_id": "cam_01",
                "camera_ids": ["cam_01"],
                "risk_score": 0.6,
            },
        ],
        cases=[
            {
                "case_id": "case-1",
                "title": "Possible incident",
                "description": "Requires review",
                "status": "open",
                "priority": "high",
                "severity": "critical",
                "camera_ids": ["cam_01"],
                "assigned_to": "alice",
                "requires_review": True,
                "review_status": "pending",
                "created_at": "2026-05-10T01:00:00+00:00",
                "closed_at": None,
            }
        ],
        notes=[{"note_id": "note-1", "created_at": "2026-05-10T02:00:00+00:00"}],
        case_audits=[{"actor": "alice", "action": "note_added", "timestamp": "2026-05-10T02:15:00+00:00"}],
        streams=[
            {
                "camera_id": "cam_01",
                "state": "running",
                "stream_id": "stream-cam-01",
                "health": {"status": "healthy", "fps_decode": 14.5, "fps_processed": 11.8},
                "stats": {
                    "fps_decode": 14.5,
                    "fps_processed": 11.8,
                    "dropped_frames_total": 3,
                    "reconnect_attempts": 1,
                    "offline_transitions": 1,
                    "preview_clients_active": 2,
                    "last_frame_at": "2026-05-10T02:20:00+00:00",
                },
            }
        ],
        models=[
            {
                "model_key": "phone_detector",
                "display_name": "Phone Detector",
                "status": "healthy",
                "avg_latency_ms": 18.4,
                "p95_latency_ms": 24.0,
                "avg_confidence": 0.81,
                "event_count": 7,
                "benchmark_metrics": {"precision": 0.91},
                "source": "runtime",
            }
        ],
        audits=[{"username": "alice", "action": "case_note_added"}],
        system={
            "metrics": {"avg_inference_time_ms": 22.5, "stream_processing_latency_ms": 11.2},
            "system": {"model_health_status": {"phone_detector": "loaded"}},
            "event_bus": {"status": "healthy"},
            "streaming": {"streaming": {"active_streams": 1, "status": "healthy"}},
        },
    )
    service = AnalyticsService(repository=repository, config=_config())

    monkeypatch.setattr(
        "app.services.hls_service.get_hls_service",
        lambda: SimpleNamespace(get_playlist_info=lambda camera_id: SimpleNamespace(available=camera_id == "cam_01")),
    )
    monkeypatch.setattr(
        "app.services.webrtc_service.get_webrtc_service",
        lambda: SimpleNamespace(get_status=lambda camera_id: {"enabled": camera_id == "cam_01"}),
    )

    points = service.get_event_timeseries(
        {"start": "2026-05-10T01:00:00+00:00", "end": "2026-05-10T03:00:00+00:00", "bucket": "1h"},
        "1h",
        {},
    )
    streams = service.get_stream_reliability(None, {})
    workload = service.get_operator_workload(None, {})
    models = service.get_model_performance(None, {})

    assert [point.total_events for point in points] == [1, 1]
    assert streams[0].hls_available is True
    assert streams[0].webrtc_enabled is True
    assert streams[0].preview_clients == 2
    assert workload[0].operator_id == "alice"
    assert workload[0].notes_added == 2
    assert models[0].avg_latency_ms == 18.4
