from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.security_dependencies import require_permission as require_api_permission
from app.models.analytics_models import AnalyticsExportRequest, AnalyticsTimeRange
from app.models.security_models import AuditAction, UserAccount
from app.services.audit_log_service import get_audit_log_service

router = APIRouter()


def get_analytics_service():
    from app.services.analytics_service import get_analytics_service as _service_getter

    return _service_getter()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid ISO-8601 datetime: {value}")
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _analytics_query(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    bucket: str | None = Query(default=None),
    camera_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    identity_id: str | None = Query(default=None),
    incident_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    requires_review: bool | None = Query(default=None),
    user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=5000),
) -> dict[str, Any]:
    end_dt = _parse_datetime(end) or _now_utc()
    start_dt = _parse_datetime(start) or (end_dt - timedelta(hours=24))
    time_range = AnalyticsTimeRange(
        start=_to_iso(start_dt),
        end=_to_iso(end_dt),
        bucket=bucket or "1h",
    )
    filters = {
        "camera_id": camera_id,
        "severity": severity,
        "event_type": event_type,
        "status": status,
        "assigned_to": assigned_to,
        "identity_id": identity_id,
        "incident_id": incident_id,
        "review_status": review_status,
        "requires_review": requires_review,
        "user_id": user_id,
        "action": action,
        "q": q,
        "limit": limit,
    }
    return {
        "time_range": time_range,
        "filters": {key: value for key, value in filters.items() if value is not None and value != ""},
    }


def _dump_item(item: Any) -> Any:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return item


def _item_response(item: Any) -> dict[str, Any]:
    payload = _dump_item(item)
    return {"item": payload, "status": "ok" if payload is not None else "empty"}


def _list_response(items: list[Any]) -> dict[str, Any]:
    payload = [_dump_item(item) for item in items]
    return {"items": payload, "count": len(payload), "status": "ok" if payload else "empty"}


def _increment_metric(name: str, count: int = 1) -> None:
    try:
        from inference.monitoring.metrics import get_metrics

        get_metrics().increment(name, count)
    except Exception:
        pass
    try:
        from inference.metrics import metrics as core_metrics

        core_metrics.increment(name, count)
    except Exception:
        pass


def _record_latency(value_ms: float) -> None:
    rounded = round(max(0.0, value_ms), 2)
    try:
        from inference.monitoring.metrics import get_metrics

        metrics = get_metrics()
        if hasattr(metrics, "record_segmentation_value"):
            metrics.record_segmentation_value("analytics_query_latency_ms", rounded)
    except Exception:
        pass
    try:
        from inference.metrics import metrics as core_metrics

        if hasattr(core_metrics, "set_value"):
            core_metrics.set_value("analytics_query_latency_ms", rounded)
    except Exception:
        pass


def _execute(name: str, fn):
    started = time.perf_counter()
    _increment_metric("analytics_requests_total")
    try:
        return fn()
    except HTTPException:
        _increment_metric("analytics_failures_total")
        raise
    except Exception as exc:
        _increment_metric("analytics_failures_total")
        raise HTTPException(status_code=500, detail=f"Analytics request failed for {name}: {exc}")
    finally:
        _record_latency((time.perf_counter() - started) * 1000.0)


@router.get("/api/analytics/overview")
def get_analytics_overview_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("overview", lambda: _item_response(service.get_dashboard_overview(params["time_range"], params["filters"])))


@router.get("/api/analytics/events/timeseries")
def get_analytics_event_timeseries_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("events_timeseries", lambda: _list_response(service.get_event_timeseries(params["time_range"], params["time_range"].bucket, params["filters"])))


@router.get("/api/analytics/events/by-type")
def get_analytics_events_by_type_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("events_by_type", lambda: _list_response(service.get_events_by_type(params["time_range"], params["filters"])))


@router.get("/api/analytics/cases/summary")
def get_analytics_case_summary_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("cases_summary", lambda: _item_response(service.get_case_summary(params["time_range"], params["filters"])))


@router.get("/api/analytics/cases/timeseries")
def get_analytics_case_timeseries_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("cases_timeseries", lambda: _list_response(service.get_case_timeseries(params["time_range"], params["time_range"].bucket, params["filters"])))


@router.get("/api/analytics/cameras/risk")
def get_analytics_camera_risk_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("cameras_risk", lambda: _list_response(service.get_camera_risk(params["time_range"], params["filters"])))


@router.get("/api/analytics/cameras/heatmap")
def get_analytics_camera_heatmap_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("cameras_heatmap", lambda: _list_response(service.get_camera_risk_heatmap(params["time_range"], params["filters"])))


@router.get("/api/analytics/models/performance")
def get_analytics_model_performance_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("models_performance", lambda: _list_response(service.get_model_performance(params["time_range"], params["filters"])))


@router.get("/api/analytics/anomaly/trends")
def get_analytics_anomaly_trends_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("anomaly_trends", lambda: _item_response(service.get_anomaly_trends(params["time_range"], params["filters"])))


@router.get("/api/analytics/identity/summary")
def get_analytics_identity_summary_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("identity_summary", lambda: _item_response(service.get_identity_summary(params["time_range"], params["filters"])))


@router.get("/api/analytics/open-vocab/summary")
def get_analytics_open_vocab_summary_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("open_vocab_summary", lambda: _item_response(service.get_open_vocab_summary(params["time_range"], params["filters"])))


@router.get("/api/analytics/streams/reliability")
def get_analytics_stream_reliability_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("streams_reliability", lambda: _list_response(service.get_stream_reliability(params["time_range"], params["filters"])))


@router.get("/api/analytics/operators/workload")
def get_analytics_operator_workload_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("operators_workload", lambda: _list_response(service.get_operator_workload(params["time_range"], params["filters"])))


@router.get("/api/analytics/system/performance")
def get_analytics_system_performance_api(
    params: dict[str, Any] = Depends(_analytics_query),
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("system_performance", lambda: _item_response(service.get_system_performance(params["time_range"], params["filters"])))


@router.post("/api/analytics/export")
def export_analytics_api(
    body: AnalyticsExportRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("analytics:export")),
):
    service = get_analytics_service()

    def _run():
        export = service.export_analytics(body)
        get_audit_log_service().record(
            AuditAction.ANALYTICS_EXPORTED,
            user=current_user,
            resource_type="analytics_export",
            resource_id=export.export_id,
            detail=f"Analytics export generated as {export.format}",
            request=request,
            metadata={
                "format": export.format,
                "filename": export.filename,
                "sections": body.sections,
                "time_range": body.time_range.model_dump(mode="json"),
            },
        )
        return _item_response(export)

    return _execute("export", _run)


@router.get("/api/analytics/health")
def analytics_health_api(
    current_user: UserAccount = Depends(require_api_permission("analytics:read")),
):
    del current_user
    service = get_analytics_service()
    return _execute("health", lambda: _item_response(service.get_health()))
