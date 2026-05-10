from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.models.analytics_models import AnalyticsTimeRange
from app.repositories import analytics_repository as analytics_repository_module
from app.repositories.analytics_repository import AnalyticsRepository


class _CaseRepository:
    def __init__(self):
        self._health = {
            "enabled": True,
            "storage": "jsonl",
            "status": "healthy",
            "case_count": 0,
            "open_case_count": 0,
            "last_error": None,
        }

    def health(self):
        return dict(self._health)

    def list_cases(self, filters):
        del filters
        return []

    def list_evidence(self, case_id):
        del case_id
        return []

    def list_notes(self, case_id):
        del case_id
        return []

    def list_audit_logs(self, case_id):
        del case_id
        return []


class _AuditService:
    def list_logs(self, **kwargs):
        del kwargs
        return []


class _IdentityDb:
    def get_events(self, limit=5000):
        del limit
        return [
            {
                "event_id": "db-1",
                "event_type": "possible_match",
                "timestamp": "2026-05-10T01:00:00+00:00",
                "severity": "high",
                "confidence": 0.76,
                "metadata": {"camera_ids": ["cam_01"]},
            }
        ]


class _EventBus:
    def replay_recent(self, limit=2000):
        del limit
        return [
            {
                "event_id": "bus-1",
                "event_type": "possible_incident",
                "timestamp": "2026-05-10T02:00:00+00:00",
                "severity": "critical",
                "confidence": 0.91,
                "camera_id": "cam_02",
            }
        ]

    def health(self):
        return {"status": "healthy"}


class _StreamManager:
    def list_stream_states(self):
        return [{"camera_id": "cam_01", "state": "running", "health": {"status": "healthy"}, "stats": {}}]


class _RuntimeStreamManager:
    def health_summary(self):
        return {"streaming": {"status": "healthy", "active_streams": 1, "degraded_streams": 0}}


class _MonitoringMetrics:
    def snapshot(self):
        return {}

    def increment(self, name, count=1):
        del name, count


class _IdentityStore:
    def list_identities(self, **kwargs):
        del kwargs
        return []

    def list_matches(self, **kwargs):
        del kwargs
        return []


class _GlobalRegistry:
    def list_records(self, **kwargs):
        del kwargs
        return []


class _Runtime:
    def get_open_vocab_results(self, **kwargs):
        del kwargs
        return {"status": "unavailable", "items": []}


def _time_range():
    return AnalyticsTimeRange(
        start="2026-05-10T00:00:00+00:00",
        end="2026-05-10T04:00:00+00:00",
        bucket="1h",
    )


def test_repository_get_events_merges_db_and_bus_records():
    repository = AnalyticsRepository(
        config={"analytics": {"enabled": True, "sources": {"events": True, "cases": True, "evidence": True}}},
        case_repository=_CaseRepository(),
        audit_service=_AuditService(),
        identity_db=_IdentityDb(),
        event_bus=_EventBus(),
        runtime_stream_manager=_RuntimeStreamManager(),
        stream_session_manager=_StreamManager(),
        monitoring_metrics=_MonitoringMetrics(),
        system_snapshot_provider=lambda: {},
        identity_store=_IdentityStore(),
        global_registry=_GlobalRegistry(),
        runtime=_Runtime(),
    )

    items = repository.get_events(_time_range(), {"limit": 50})

    assert [item["event_id"] for item in items] == ["bus-1", "db-1"]
    assert items[0]["camera_id"] == "cam_02"
    assert repository.get_source_statuses()["events"] == "healthy"


def test_repository_probe_sources_reports_missing_optional_dev_sources(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        monkeypatch.setattr(analytics_repository_module, "PROJECT_ROOT", Path(temp_dir))
        repository = AnalyticsRepository(
            config={
                "analytics": {
                    "enabled": True,
                    "sources": {
                        "events": True,
                        "cases": True,
                        "open_vocab": True,
                        "model_metrics": True,
                    },
                }
            },
            case_repository=_CaseRepository(),
            audit_service=_AuditService(),
            identity_db=_IdentityDb(),
            event_bus=_EventBus(),
            runtime_stream_manager=_RuntimeStreamManager(),
            stream_session_manager=_StreamManager(),
            monitoring_metrics=_MonitoringMetrics(),
            system_snapshot_provider=lambda: {},
            identity_store=_IdentityStore(),
            global_registry=_GlobalRegistry(),
            runtime=_Runtime(),
        )

        statuses = repository.probe_sources()

        assert statuses["cases"] == "healthy"
        assert statuses["open_vocab"] == "missing"
        assert statuses["model_metrics"] == "missing"
