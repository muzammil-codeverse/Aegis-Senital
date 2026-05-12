from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.object_authorization import ensure_camera_access
from app.api.security_dependencies import require_permission
from app.models.gis_models import (
    CameraGeoProfile,
    GeoFenceCreateRequest,
    GeoFenceUpdateRequest,
    GeoFenceZone,
    MapViewportRequest,
)
from app.models.security_models import AuditAction, UserAccount
from app.repositories.gis_repository import get_gis_repository, new_zone_id
from app.services.audit_log_service import get_audit_log_service
from app.services.gis_service import (
    build_map_layers,
    compute_camera_fov_polygon,
    find_nearby_cameras,
    normalize_profile,
    public_gis_config,
    validate_coordinates,
)
from inference.metrics import metrics

router = APIRouter(tags=["gis"])


def _gis_metrics_start() -> float:
    return time.perf_counter()


def _gis_metrics_end(start: float, *, failed: bool = False, markers: int = 0, heatmap_cells: int = 0) -> None:
    try:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        metrics.increment("gis_requests_total")
        metrics.set_value("gis_query_latency_ms", int(max(0.0, elapsed_ms)))
        if failed:
            metrics.increment("gis_failures_total")
        if markers:
            metrics.increment("gis_markers_returned_total", markers)
        if heatmap_cells:
            metrics.increment("gis_heatmap_cells_total", heatmap_cells)
    except Exception:
        pass


@router.get("/api/gis/config")
def get_gis_config_api(
    request: Request,
    current_user: UserAccount = Depends(require_permission("gis:read")),
):
    del request, current_user
    t0 = _gis_metrics_start()
    try:
        item = public_gis_config().model_dump(mode="json")
        _gis_metrics_end(t0)
        return {"item": item, "status": "ok"}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/cameras")
def list_gis_cameras_api(
    request: Request,
    current_user: UserAccount = Depends(require_permission("gis:read")),
):
    t0 = _gis_metrics_start()
    try:
        repo = get_gis_repository()
        items = [p.model_dump(mode="json") for p in repo.list_camera_geo_profiles(current_user)]
        _gis_metrics_end(t0, markers=len(items))
        return {"items": items, "count": len(items), "status": "ok"}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/cameras/{camera_id}")
def get_gis_camera_api(
    request: Request,
    camera_id: str,
    current_user: UserAccount = Depends(require_permission("gis:read")),
):
    t0 = _gis_metrics_start()
    try:
        ensure_camera_access(request, current_user, camera_id)
        profile = get_gis_repository().get_camera_geo_profile(camera_id)
        if profile is None:
            _gis_metrics_end(t0)
            return {"item": None, "status": "not_found"}
        _gis_metrics_end(t0, markers=1)
        return {"item": profile.model_dump(mode="json"), "status": "ok"}
    except HTTPException as exc:
        if exc.status_code == 403:
            try:
                get_audit_log_service().record(
                    AuditAction.GIS_CAMERA_PROFILE_ACCESS_DENIED,
                    user=current_user,
                    resource_type="camera_geo",
                    resource_id=camera_id,
                    success=False,
                    detail="GIS camera profile access denied",
                    request=request,
                )
            except Exception:
                pass
        _gis_metrics_end(t0, failed=True)
        raise
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.put("/api/gis/cameras/{camera_id}")
def put_gis_camera_api(
    request: Request,
    camera_id: str,
    payload: dict[str, Any],
    current_user: UserAccount = Depends(require_permission("gis:write")),
):
    t0 = _gis_metrics_start()
    try:
        ensure_camera_access(request, current_user, camera_id)
        body = dict(payload or {})
        body["camera_id"] = camera_id
        profile = CameraGeoProfile.model_validate(body)
        validate_coordinates(profile.latitude, profile.longitude)
        profile = normalize_profile(profile)
        repo = get_gis_repository()
        saved = repo.upsert_camera_geo_profile(profile)
        get_audit_log_service().record(
            AuditAction.GIS_CAMERA_PROFILE_UPDATED,
            user=current_user,
            resource_type="camera_geo",
            resource_id=camera_id,
            detail="GIS camera geo profile updated",
            request=request,
        )
        _gis_metrics_end(t0)
        return {"item": saved.model_dump(mode="json"), "status": "ok"}
    except ValueError as exc:
        _gis_metrics_end(t0, failed=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException as exc:
        if exc.status_code == 403:
            try:
                get_audit_log_service().record(
                    AuditAction.GIS_CAMERA_PROFILE_ACCESS_DENIED,
                    user=current_user,
                    resource_type="camera_geo",
                    resource_id=camera_id,
                    success=False,
                    detail="GIS camera profile update denied",
                    request=request,
                )
            except Exception:
                pass
        _gis_metrics_end(t0, failed=True)
        raise
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/cameras/{camera_id}/fov")
def get_gis_camera_fov_api(
    request: Request,
    camera_id: str,
    current_user: UserAccount = Depends(require_permission("gis:read")),
):
    t0 = _gis_metrics_start()
    try:
        ensure_camera_access(request, current_user, camera_id)
        profile = get_gis_repository().get_camera_geo_profile(camera_id)
        if profile is None:
            _gis_metrics_end(t0)
            return {"item": None, "status": "not_found"}
        poly = compute_camera_fov_polygon(profile)
        _gis_metrics_end(t0, markers=len(poly))
        return {
            "item": {
                "camera_id": camera_id,
                "polygon": [p.model_dump(mode="json") for p in poly],
            },
            "status": "ok",
        }
    except HTTPException:
        _gis_metrics_end(t0, failed=True)
        raise
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/nearby-cameras")
def get_nearby_cameras_api(
    request: Request,
    current_user: UserAccount = Depends(require_permission("gis:read")),
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius_meters: float = Query(500.0, ge=1.0, le=50_000.0),
):
    del request
    t0 = _gis_metrics_start()
    try:
        metrics.increment("gis_nearby_camera_queries_total")
        items = find_nearby_cameras(get_gis_repository(), current_user, latitude, longitude, radius_meters)
        _gis_metrics_end(t0, markers=len(items))
        return {"items": [i.model_dump(mode="json") for i in items], "count": len(items), "status": "ok"}
    except ValueError as exc:
        _gis_metrics_end(t0, failed=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/events")
def get_gis_events_api(
    request: Request,
    current_user: UserAccount = Depends(require_permission("gis:read")),
    start_time: str | None = None,
    end_time: str | None = None,
    severity: str | None = None,
    event_type: str | None = None,
    camera_id: str | None = None,
    case_id: str | None = None,
    source_type: str | None = None,
):
    del request
    t0 = _gis_metrics_start()
    try:
        items = get_gis_repository().get_event_markers(
            user=current_user,
            start_time=start_time,
            end_time=end_time,
            severity=severity,
            event_type=event_type,
            camera_id=camera_id,
            case_id=case_id,
            source_type=source_type,
        )
        _gis_metrics_end(t0, markers=len(items))
        return {"items": [i.model_dump(mode="json") for i in items], "count": len(items), "status": "ok"}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/cases")
def get_gis_cases_api(
    request: Request,
    current_user: UserAccount = Depends(require_permission("gis:read")),
    start_time: str | None = None,
    end_time: str | None = None,
    severity: str | None = None,
    camera_id: str | None = None,
    case_id: str | None = None,
):
    del request
    t0 = _gis_metrics_start()
    try:
        items = get_gis_repository().get_case_markers(
            user=current_user,
            start_time=start_time,
            end_time=end_time,
            severity=severity,
            camera_id=camera_id,
            case_id=case_id,
        )
        _gis_metrics_end(t0, markers=len(items))
        return {"items": [i.model_dump(mode="json") for i in items], "count": len(items), "status": "ok"}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/heatmap")
def get_gis_heatmap_api(
    request: Request,
    current_user: UserAccount = Depends(require_permission("gis:read")),
    start_time: str | None = None,
    end_time: str | None = None,
    severity: str | None = None,
    event_type: str | None = None,
    camera_id: str | None = None,
    case_id: str | None = None,
    source_type: str | None = None,
):
    del request
    t0 = _gis_metrics_start()
    try:
        cells = get_gis_repository().compute_risk_heatmap(
            current_user,
            start_time,
            end_time,
            severity,
            event_type,
            camera_id,
            case_id,
            source_type,
        )
        _gis_metrics_end(t0, heatmap_cells=len(cells))
        return {"items": [c.model_dump(mode="json") for c in cells], "count": len(cells), "status": "ok"}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/layers")
def get_gis_layers_api(
    request: Request,
    current_user: UserAccount = Depends(require_permission("gis:read")),
    start_time: str | None = None,
    end_time: str | None = None,
    severity: str | None = None,
    event_type: str | None = None,
    camera_id: str | None = None,
    case_id: str | None = None,
    source_type: str | None = None,
    north: float | None = None,
    south: float | None = None,
    east: float | None = None,
    west: float | None = None,
    zoom: float | None = None,
):
    del request
    t0 = _gis_metrics_start()
    try:
        vp = MapViewportRequest(north=north, south=south, east=east, west=west, zoom=zoom)
        layers = build_map_layers(
            get_gis_repository(),
            current_user,
            vp,
            start_time=start_time,
            end_time=end_time,
            severity=severity,
            event_type=event_type,
            camera_id=camera_id,
            case_id=case_id,
            source_type=source_type,
        )
        mcount = len(layers.event_markers) + len(layers.case_markers)
        _gis_metrics_end(t0, markers=mcount, heatmap_cells=len(layers.heatmap_cells))
        return {"item": layers.model_dump(mode="json"), "status": "ok"}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/geofences")
def list_geofences_api(
    request: Request,
    current_user: UserAccount = Depends(require_permission("gis:read")),
):
    del request
    t0 = _gis_metrics_start()
    try:
        items = get_gis_repository().list_geofences(current_user)
        _gis_metrics_end(t0, markers=len(items))
        return {"items": [z.model_dump(mode="json") for z in items], "count": len(items), "status": "ok"}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.post("/api/gis/geofences")
def create_geofence_api(
    request: Request,
    body: GeoFenceCreateRequest,
    current_user: UserAccount = Depends(require_permission("gis:write")),
):
    t0 = _gis_metrics_start()
    try:
        zone = GeoFenceZone.model_validate({**body.model_dump(), "zone_id": new_zone_id()})
        if len(zone.polygon) < 3:
            raise HTTPException(status_code=400, detail="polygon must have at least 3 points")
        saved = get_gis_repository().create_geofence(zone)
        get_audit_log_service().record(
            AuditAction.GIS_GEOFENCE_CREATED,
            user=current_user,
            resource_type="geofence",
            resource_id=saved.zone_id,
            detail="Geofence created",
            request=request,
        )
        try:
            metrics.increment("gis_geofences_total")
        except Exception:
            pass
        _gis_metrics_end(t0)
        return {"item": saved.model_dump(mode="json"), "status": "ok"}
    except HTTPException:
        _gis_metrics_end(t0, failed=True)
        raise
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.get("/api/gis/geofences/{zone_id}")
def get_geofence_api(
    request: Request,
    zone_id: str,
    current_user: UserAccount = Depends(require_permission("gis:read")),
):
    del request, current_user
    t0 = _gis_metrics_start()
    try:
        zone = get_gis_repository().get_geofence(zone_id)
        if zone is None:
            _gis_metrics_end(t0)
            return {"item": None, "status": "not_found"}
        _gis_metrics_end(t0)
        return {"item": zone.model_dump(mode="json"), "status": "ok"}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.patch("/api/gis/geofences/{zone_id}")
def patch_geofence_api(
    request: Request,
    zone_id: str,
    body: GeoFenceUpdateRequest,
    current_user: UserAccount = Depends(require_permission("gis:write")),
):
    t0 = _gis_metrics_start()
    try:
        updated = get_gis_repository().update_geofence(zone_id, body.model_dump(exclude_none=True))
        if updated is None:
            _gis_metrics_end(t0)
            return {"item": None, "status": "not_found"}
        get_audit_log_service().record(
            AuditAction.GIS_GEOFENCE_UPDATED,
            user=current_user,
            resource_type="geofence",
            resource_id=zone_id,
            detail="Geofence updated",
            request=request,
        )
        try:
            metrics.increment("gis_geofences_total")
        except Exception:
            pass
        _gis_metrics_end(t0)
        return {"item": updated.model_dump(mode="json"), "status": "ok"}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise


@router.delete("/api/gis/geofences/{zone_id}")
def delete_geofence_api(
    request: Request,
    zone_id: str,
    current_user: UserAccount = Depends(require_permission("gis:write")),
):
    t0 = _gis_metrics_start()
    try:
        ok = get_gis_repository().delete_geofence(zone_id)
        if not ok:
            _gis_metrics_end(t0)
            return {"status": "not_found", "deleted": False}
        get_audit_log_service().record(
            AuditAction.GIS_GEOFENCE_DELETED,
            user=current_user,
            resource_type="geofence",
            resource_id=zone_id,
            detail="Geofence deleted",
            request=request,
        )
        try:
            metrics.increment("gis_geofences_total")
        except Exception:
            pass
        _gis_metrics_end(t0)
        return {"status": "ok", "deleted": True}
    except Exception:
        _gis_metrics_end(t0, failed=True)
        raise
