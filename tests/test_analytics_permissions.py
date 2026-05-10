from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import analytics_routes
from app.models.analytics_models import AnalyticsExportResponse
from app.services.auth_service import get_auth_service
from analytics_test_utils import build_analytics_test_app, make_user


class _PermissionService:
    def get_dashboard_overview(self, time_range, filters):
        del time_range, filters
        return {
            "time_range": {
                "start": "2026-05-10T00:00:00+00:00",
                "end": "2026-05-10T01:00:00+00:00",
                "bucket": "1h",
            },
            "summary": {
                "total_events": 0,
                "critical_events": 0,
                "open_cases": 0,
                "cases_requiring_review": 0,
                "active_streams": 0,
                "degraded_streams": 0,
                "avg_model_latency_ms": 0.0,
            },
            "risk": {"highest_risk_camera": None, "highest_risk_score": 0.0},
            "source_status": {"events": "healthy"},
        }

    def export_analytics(self, request):
        del request
        return AnalyticsExportResponse(
            export_id="exp-1",
            format="json",
            filename="exp-1.json",
            content_type="application/json",
            generated_at="2026-05-10T00:00:00+00:00",
            content="{}",
        )


def test_analytics_permissions_allow_read_but_protect_export(monkeypatch):
    monkeypatch.setattr(analytics_routes, "get_analytics_service", lambda: _PermissionService())
    users = {
        "viewer": make_user("viewer"),
        "supervisor": make_user("supervisor"),
    }
    monkeypatch.setattr(get_auth_service(), "get_current_user_from_token", lambda token: users.get(token))

    client = TestClient(build_analytics_test_app(), raise_server_exceptions=False)

    read_response = client.get("/api/analytics/overview", headers={"Authorization": "Bearer viewer"})
    denied_export = client.post(
        "/api/analytics/export",
        headers={"Authorization": "Bearer viewer"},
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
    allowed_export = client.post(
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

    assert read_response.status_code == 200
    assert denied_export.status_code == 403
    assert allowed_export.status_code == 200
