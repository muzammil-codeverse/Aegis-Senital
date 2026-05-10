from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import analytics_routes
from app.models.analytics_models import AnalyticsExportRequest, AnalyticsExportResponse, AnalyticsTimeRange
from app.models.security_models import AuditAction
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import get_auth_service
from analytics_test_utils import build_analytics_test_app, make_user


class _ExportRepository:
    enabled = True
    storage_backend = "jsonl"

    def get_events(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_cases(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_evidence(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_case_notes(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_case_audit_logs(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_stream_health(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_model_metrics(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_audit_activity(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_identity_profiles(self, filters=None):
        del filters
        return []

    def get_identity_matches(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_global_identity_records(self, filters=None):
        del filters
        return []

    def get_open_vocab_results(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_system_metrics(self):
        return {"metrics": {}, "system": {}, "event_bus": {}, "streaming": {"streaming": {}}}

    def get_source_statuses(self):
        return {"events": "healthy"}

    def probe_sources(self):
        return {"events": "healthy"}

    def get_last_error(self):
        return None


class _RouteExportService:
    def export_analytics(self, request):
        payload = request if isinstance(request, AnalyticsExportRequest) else AnalyticsExportRequest.model_validate(request)
        return AnalyticsExportResponse(
            export_id="analytics_export_1",
            format=payload.format,
            filename=f"analytics_export_1.{payload.format}",
            content_type="application/json" if payload.format == "json" else "text/csv",
            generated_at="2026-05-10T00:00:00+00:00",
            content="{}" if payload.format == "json" else "section,field,value\n",
        )


def test_export_service_supports_json_and_csv_formats():
    service = AnalyticsService(
        repository=_ExportRepository(),
        config={"analytics": {"enabled": True, "cache": {"enabled": False}}},
    )
    request = AnalyticsExportRequest(
        format="json",
        sections=["overview"],
        time_range=AnalyticsTimeRange(
            start="2026-05-10T00:00:00+00:00",
            end="2026-05-10T01:00:00+00:00",
        ),
    )

    json_export = service.export_analytics(request)
    csv_export = service.export_analytics(request.model_copy(update={"format": "csv"}))

    assert json_export.filename.endswith(".json")
    assert "\"overview\"" in json_export.content
    assert csv_export.filename.endswith(".csv")
    assert "section,field,value" in csv_export.content


def test_export_route_audit_logs_exports(monkeypatch):
    recorded = []
    monkeypatch.setattr(analytics_routes, "get_analytics_service", lambda: _RouteExportService())
    monkeypatch.setattr(
        analytics_routes,
        "get_audit_log_service",
        lambda: type("AuditSpy", (), {"record": staticmethod(lambda *args, **kwargs: recorded.append((args, kwargs)))})(),
    )
    monkeypatch.setattr(get_auth_service(), "get_current_user_from_token", lambda token: make_user("supervisor") if token == "supervisor" else None)

    client = TestClient(build_analytics_test_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/analytics/export",
        headers={"Authorization": "Bearer supervisor"},
        json={
            "format": "json",
            "sections": ["overview"],
            "time_range": {
                "start": "2026-05-10T00:00:00+00:00",
                "end": "2026-05-10T01:00:00+00:00",
                "bucket": "1h",
            },
            "filters": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["item"]["filename"].endswith(".json")
    assert recorded[0][0][0] == AuditAction.ANALYTICS_EXPORTED
