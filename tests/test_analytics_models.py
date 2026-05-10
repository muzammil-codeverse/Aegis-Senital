from app.models.analytics_models import (
    AnalyticsExportRequest,
    AnalyticsTimeRange,
    DashboardOverview,
    DashboardRisk,
    DashboardSummary,
)


def test_dashboard_overview_serializes_nested_summary():
    overview = DashboardOverview(
        time_range=AnalyticsTimeRange(
            start="2026-05-10T00:00:00+00:00",
            end="2026-05-10T12:00:00+00:00",
            bucket="1h",
        ),
        summary=DashboardSummary(
            total_events=12,
            critical_events=2,
            open_cases=3,
            cases_requiring_review=1,
            active_streams=4,
            degraded_streams=1,
            avg_model_latency_ms=24.8,
        ),
        risk=DashboardRisk(highest_risk_camera="cam_03", highest_risk_score=82.4),
        source_status={"events": "healthy"},
    )

    payload = overview.model_dump(mode="json")

    assert payload["summary"]["total_events"] == 12
    assert payload["risk"]["highest_risk_camera"] == "cam_03"
    assert payload["time_range"]["bucket"] == "1h"


def test_analytics_export_request_defaults_are_operator_safe():
    request = AnalyticsExportRequest(
        time_range=AnalyticsTimeRange(
            start="2026-05-09T00:00:00+00:00",
            end="2026-05-10T00:00:00+00:00",
        )
    )

    assert request.format == "json"
    assert request.sections == []
    assert request.filters == {}
