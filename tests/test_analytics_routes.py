from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import analytics_routes
from app.models.analytics_models import (
    AnalyticsHealthReport,
    AnalyticsTimeRange,
    DashboardOverview,
    DashboardRisk,
    DashboardSummary,
    EventTimeseriesPoint,
    ModelPerformanceSummary,
)
from app.services.auth_service import get_auth_service
from analytics_test_utils import build_analytics_test_app, make_user


class _RouteService:
    def get_dashboard_overview(self, time_range, filters):
        del time_range, filters
        return DashboardOverview(
            time_range=AnalyticsTimeRange(
                start="2026-05-10T00:00:00+00:00",
                end="2026-05-10T12:00:00+00:00",
            ),
            summary=DashboardSummary(total_events=8, critical_events=2, open_cases=3, cases_requiring_review=1, active_streams=2, degraded_streams=0, avg_model_latency_ms=18.2),
            risk=DashboardRisk(highest_risk_camera="cam_02", highest_risk_score=41.6),
            source_status={"events": "healthy"},
        )

    def get_event_timeseries(self, time_range, bucket, filters):
        del time_range, bucket, filters
        return [
            EventTimeseriesPoint(
                bucket_start="2026-05-10T00:00:00+00:00",
                bucket_end="2026-05-10T01:00:00+00:00",
                total_events=4,
                critical_events=1,
                high_events=1,
                possible_incidents=2,
                avg_confidence=0.75,
            )
        ]

    def get_model_performance(self, time_range, filters):
        del time_range, filters
        return [
            ModelPerformanceSummary(
                model_key="phone_detector",
                display_name="Phone Detector",
                status="healthy",
                avg_latency_ms=17.8,
                p95_latency_ms=24.0,
                avg_confidence=0.82,
                event_count=4,
                benchmark_metrics={"precision": 0.91},
                source="runtime",
            )
        ]

    def get_health(self):
        return AnalyticsHealthReport(
            enabled=True,
            status="healthy",
            storage="jsonl",
            sources={"events": "healthy"},
            last_error=None,
        )


def test_analytics_routes_return_structured_payloads(monkeypatch):
    monkeypatch.setattr(analytics_routes, "get_analytics_service", lambda: _RouteService())
    monkeypatch.setattr(get_auth_service(), "get_current_user_from_token", lambda token: make_user("viewer") if token == "viewer" else None)

    client = TestClient(build_analytics_test_app(), raise_server_exceptions=False)

    overview = client.get("/api/analytics/overview", headers={"Authorization": "Bearer viewer"})
    timeseries = client.get("/api/analytics/events/timeseries", headers={"Authorization": "Bearer viewer"})
    performance = client.get("/api/analytics/models/performance", headers={"Authorization": "Bearer viewer"})
    health = client.get("/api/analytics/health", headers={"Authorization": "Bearer viewer"})

    assert overview.status_code == 200
    assert overview.json()["item"]["summary"]["total_events"] == 8
    assert timeseries.json()["count"] == 1
    assert performance.json()["items"][0]["model_key"] == "phone_detector"
    assert health.json()["item"]["status"] == "healthy"
