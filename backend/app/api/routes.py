import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from app.services.video_service import extract_frames
from app.core.config import load_scenario_config
from app.core.logging_config import logger
from app.services.intelligence_response_builder import IntelligenceResponseBuilder
from inference.identity_db import get_db
from inference.metrics import metrics
from inference.monitoring.metrics import get_metrics
from inference.runtime import get_intelligence_runtime

router = APIRouter()

VALID_SCENARIOS = ("security", "classroom", "traffic")


# ── Stream request/response models ────────────────────────────────────────────

class StreamAddRequest(BaseModel):
    source: str
    stream_id: str | None = None


class StreamRemoveRequest(BaseModel):
    stream_id: str


class AlertActionRequest(BaseModel):
    operator_id: str | None = None
    reason: str | None = None


class CameraCreateRequest(BaseModel):
    camera_id: str
    name: str
    source_type: str = "mock"
    source_uri: str | None = None
    location: dict | None = None
    zone: str | None = None
    priority: str = "normal"
    enabled: bool = True
    metadata: dict | None = None


class CameraUpdateRequest(BaseModel):
    name: str | None = None
    source_type: str | None = None
    source_uri: str | None = None
    location: dict | None = None
    zone: str | None = None
    priority: str | None = None
    enabled: bool | None = None
    metadata: dict | None = None


@router.get("/health")
def health_check():
    from app.services.video_service import _engine, _runtime_db, _identity_fusion
    from inference.stream.stream_manager import get_stream_manager

    models_loaded = _engine is not None and getattr(_engine, "is_loaded", False)

    db_connected = False
    if _runtime_db is not None:
        try:
            db_connected = _runtime_db.db_healthy
        except Exception as exc:
            logger.warning("DB health check failed: %s", exc)

    identity_status: dict = {}
    if _identity_fusion is not None:
        try:
            identity_status = _identity_fusion.get_status()
        except Exception as exc:
            logger.warning("Identity status check failed: %s", exc)

    stream_health = get_stream_manager().health_summary()
    intelligence_health = get_intelligence_runtime().get_health()

    return {
        "status": "ok",
        "models_loaded": models_loaded,
        "db_connected": db_connected,
        "identity_fusion": identity_status,
        "metrics": get_metrics().snapshot(),
        "active_streams": stream_health["active_streams"],
        "total_streams": stream_health["total_streams"],
        "stream_metrics": stream_health["stream_metrics"],
        "intelligence_runtime": intelligence_health,
    }


@router.post("/process-video")
async def process_video(
    file: UploadFile = File(...),
    scenario: str = Query(default="security"),
):
    if not file.filename.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        raise HTTPException(status_code=400, detail="Unsupported video format")
    if scenario not in VALID_SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{scenario}'. Choose from: {VALID_SCENARIOS}",
        )

    logger.info(f"Received video upload: {file.filename} | scenario={scenario}")
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = extract_frames(tmp_path, scenario=scenario)
    finally:
        os.unlink(tmp_path)

    total = sum(len(f["objects"]) for f in result["detections"])
    logger.info(
        f"Process-video complete: {result['frames']} frames, {total} detections, "
        f"{result['event_summary']['confirmed']} confirmed events"
    )
    return result


@router.get("/metrics")
def get_metrics_snapshot():
    """
    Expose all system-level pipeline metrics in a single call.

    Includes frame throughput, latency, GPU utilisation estimate, queue
    overflow counts, circuit-break events, and identity-fusion statistics.
    Intended for dashboards, Prometheus scrapers, or operator alerting.
    """
    from inference.monitoring.metrics import all_stream_snapshots
    m = get_metrics().snapshot()
    m["per_stream"] = all_stream_snapshots()
    return m


@router.get("/metrics/core")
def get_core_metrics():
    return metrics.to_dict()


@router.get("/config/{scenario}")
def get_config(scenario: str):
    logger.info(f"Config requested: {scenario}")
    try:
        config = load_scenario_config(scenario)
        return config
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario}' not found")


@router.get("/events")
def list_events():
    logger.info("Events list requested")
    events = get_db().get_events(limit=50)
    return [
        {
            "id": e.get("event_id"),
            "timestamp": e.get("timestamp"),
            "type": e.get("event_type"),
            "severity": e.get("severity"),
            "confidence": e.get("confidence"),
            "metadata": e.get("metadata", {}),
        }
        for e in events
    ]


@router.get("/detections")
def list_detections():
    logger.info("Detections list requested")
    tracks = get_db().get_tracks(limit=50)
    return [
        {
            "id": t.get("track_id"),
            "timestamp": t.get("last_seen"),
            "type": t.get("class_name"),
            "confidence": t.get("confidence"),
            "bbox": t.get("bbox", []),
            "metadata": t.get("metadata", {}),
        }
        for t in tracks
    ]


# ── Stream management endpoints ───────────────────────────────────────────────

@router.get("/streams")
def list_streams():
    """Return status and per-stream metrics for all registered streams."""
    from inference.stream.stream_manager import get_stream_manager
    logger.info("Streams list requested")
    return get_stream_manager().list_streams()


@router.post("/streams/add")
def add_stream(body: StreamAddRequest):
    """
    Register and start a new stream.

    ``source`` may be an RTSP URL, a local camera index (as a string,
    e.g. ``"0"``), or a video file path.
    ``stream_id`` is optional — one is auto-generated when omitted.
    """
    from inference.stream.stream_manager import get_stream_manager
    logger.info("Add stream requested: source=%s stream_id=%s", body.source, body.stream_id)
    try:
        assigned_id = get_stream_manager().add_stream(
            source=body.source,
            stream_id=body.stream_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"stream_id": assigned_id, "status": "started"}


@router.post("/streams/remove")
def remove_stream(body: StreamRemoveRequest):
    """Stop and deregister a stream by its stream_id."""
    from inference.stream.stream_manager import get_stream_manager
    logger.info("Remove stream requested: stream_id=%s", body.stream_id)
    removed = get_stream_manager().remove_stream(body.stream_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Stream '{body.stream_id}' not found",
        )
    return {"stream_id": body.stream_id, "status": "stopped"}


@router.get("/api/incidents")
@router.get("/incidents")
def list_incidents_api():
    incidents = get_intelligence_runtime().get_incidents()
    return IntelligenceResponseBuilder.incident_feed(incidents)


@router.get("/api/incidents/{incident_id}")
@router.get("/incidents/{incident_id}")
def get_incident_api(incident_id: str):
    runtime = get_intelligence_runtime()
    incident = runtime.incident_engine.get_incident(incident_id)
    return IntelligenceResponseBuilder.incident_detail(incident)


@router.get("/api/timeline/{track_id}")
@router.get("/timeline/{track_id}")
def get_timeline(track_id: str):
    events = get_intelligence_runtime().get_track_timeline(track_id)
    return IntelligenceResponseBuilder.timeline(track_id, events)


@router.get("/api/anomalies/live")
@router.get("/anomalies/live")
def get_live_anomalies():
    anomalies = get_intelligence_runtime().get_live_anomalies()
    return IntelligenceResponseBuilder.anomalies(anomalies)


@router.get("/api/alerts")
def list_alerts_api(
    state: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    response = get_intelligence_runtime().get_alerts(state=state, severity=severity, limit=limit)
    return IntelligenceResponseBuilder.build_alert_feed_payload(response["items"])


@router.get("/api/alerts/live")
def live_alerts_api(limit: int = Query(default=100, ge=1, le=1000)):
    response = get_intelligence_runtime().get_live_alert_feed(limit=limit)
    return IntelligenceResponseBuilder.build_alert_feed_payload(response["items"])


@router.get("/api/alerts/operator-queue")
def operator_queue_api(limit: int = Query(default=100, ge=1, le=1000)):
    response = get_intelligence_runtime().get_live_alert_feed(limit=limit)
    return IntelligenceResponseBuilder.build_operator_queue_payload(response["items"])


@router.get("/api/alerts/{alert_id}")
def get_alert_api(alert_id: str):
    response = get_intelligence_runtime().get_alert(alert_id)
    return IntelligenceResponseBuilder.build_alert_detail_payload(response["item"])


@router.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert_api(alert_id: str, body: AlertActionRequest | None = None):
    operator_id = body.operator_id if body else None
    response = get_intelligence_runtime().acknowledge_alert(alert_id, operator_id=operator_id)
    return IntelligenceResponseBuilder.build_alert_detail_payload(response["item"])


@router.post("/api/alerts/{alert_id}/resolve")
def resolve_alert_api(alert_id: str, body: AlertActionRequest | None = None):
    operator_id = body.operator_id if body else None
    response = get_intelligence_runtime().resolve_alert(alert_id, operator_id=operator_id)
    return IntelligenceResponseBuilder.build_alert_detail_payload(response["item"])


@router.post("/api/alerts/{alert_id}/escalate")
def escalate_alert_api(alert_id: str, body: AlertActionRequest | None = None):
    reason = body.reason if body else None
    response = get_intelligence_runtime().escalate_alert(alert_id, reason=reason)
    return IntelligenceResponseBuilder.build_alert_detail_payload(response["item"])


@router.get("/api/alerts/{alert_id}/history")
def alert_history_api(alert_id: str):
    response = get_intelligence_runtime().get_alert_history(alert_id)
    return IntelligenceResponseBuilder.build_alert_history_payload(response["items"])


# ── Camera registry endpoints ─────────────────────────────────────────────────

@router.get("/api/cameras")
def list_cameras_api(
    status: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
):
    from app.services.camera_registry import get_camera_registry
    enabled_filter = enabled
    cameras = get_camera_registry().list_cameras(status=status, enabled=enabled_filter)
    items = [c.to_dict() for c in cameras]
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.post("/api/cameras")
def create_camera_api(body: CameraCreateRequest):
    from app.services.camera_registry import get_camera_registry
    try:
        camera = get_camera_registry().register_camera(body.model_dump(exclude_none=False))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=507, detail=str(exc))
    return {"item": camera.to_dict(), "status": "ok"}


@router.get("/api/cameras/latest-frames")
def list_latest_frames_api():
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    items = get_frame_snapshot_service().list_latest_frames()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/cameras/{camera_id}/status")
def get_camera_status_api(camera_id: str):
    from app.services.camera_registry import get_camera_registry
    from app.services.stream_session_manager import get_stream_session_manager
    camera = get_camera_registry().get_camera(camera_id)
    if camera is None:
        return {"item": None, "status": "not_found", "detail": f"Camera '{camera_id}' not found"}
    stream_state = get_stream_session_manager().get_stream_state(camera_id)
    return {"item": {**camera.to_dict(), "stream_session": stream_state}, "status": "ok"}


@router.get("/api/cameras/{camera_id}/latest-frame")
def get_camera_latest_frame_api(camera_id: str):
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    frame = get_frame_snapshot_service().get_latest_frame(camera_id)
    status = frame.get("status", "ok")
    return {"item": frame, "status": status}


@router.get("/api/cameras/{camera_id}/heatmap")
@router.get("/cameras/{camera_id}/heatmap")
def get_camera_heatmap(camera_id: str):
    heatmap = get_intelligence_runtime().get_camera_heatmap(camera_id)
    return IntelligenceResponseBuilder.heatmap(heatmap, camera_id)


@router.get("/api/cameras/{camera_id}")
def get_camera_api(camera_id: str):
    from app.services.camera_registry import get_camera_registry
    camera = get_camera_registry().get_camera(camera_id)
    if camera is None:
        return {"item": None, "status": "not_found", "detail": f"Camera '{camera_id}' not found"}
    return {"item": camera.to_dict(), "status": "ok"}


@router.patch("/api/cameras/{camera_id}")
def update_camera_api(camera_id: str, body: CameraUpdateRequest):
    from app.services.camera_registry import get_camera_registry
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    camera = get_camera_registry().update_camera(camera_id, updates)
    if camera is None:
        return {"item": None, "status": "not_found", "detail": f"Camera '{camera_id}' not found"}
    return {"item": camera.to_dict(), "status": "ok"}


@router.delete("/api/cameras/{camera_id}")
def delete_camera_api(camera_id: str):
    from app.services.camera_registry import get_camera_registry
    removed = get_camera_registry().remove_camera(camera_id)
    if not removed:
        return {"item": None, "status": "not_found", "detail": f"Camera '{camera_id}' not found"}
    return {"item": None, "status": "ok", "detail": f"Camera '{camera_id}' removed"}


# ── Stream session control endpoints ─────────────────────────────────────────

@router.post("/api/cameras/{camera_id}/start")
def start_camera_stream_api(camera_id: str):
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().start_stream(camera_id)
    return {"item": result, "status": "ok"}


@router.post("/api/cameras/{camera_id}/stop")
def stop_camera_stream_api(camera_id: str):
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().stop_stream(camera_id)
    return {"item": result, "status": "ok"}


@router.post("/api/cameras/{camera_id}/pause")
def pause_camera_stream_api(camera_id: str):
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().pause_stream(camera_id)
    return {"item": result, "status": "ok"}


@router.post("/api/cameras/{camera_id}/resume")
def resume_camera_stream_api(camera_id: str):
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().resume_stream(camera_id)
    return {"item": result, "status": "ok"}


@router.post("/api/cameras/{camera_id}/restart")
def restart_camera_stream_api(camera_id: str):
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().restart_stream(camera_id)
    return {"item": result, "status": "ok"}


# ── Stream session list endpoints ─────────────────────────────────────────────

@router.get("/api/streams")
def list_stream_sessions_api():
    from app.services.stream_session_manager import get_stream_session_manager
    items = get_stream_session_manager().list_stream_states()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/streams/{camera_id}")
def get_stream_session_api(camera_id: str):
    from app.services.stream_session_manager import get_stream_session_manager
    item = get_stream_session_manager().get_stream_state(camera_id)
    return {"item": item, "status": "ok"}


