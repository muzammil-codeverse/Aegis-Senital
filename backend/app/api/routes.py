import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, WebSocket
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
    base = metrics.to_dict()
    # Bridge Phase-15/16 camera metrics from registry snapshot
    try:
        from app.services.camera_registry import get_camera_registry
        snap = get_camera_registry().snapshot()
        base.update({
            "registered_cameras": snap.get("total", 0),
            "active_streams": snap.get("online", 0),
            "offline_cameras": snap.get("offline", 0),
            "degraded_cameras": snap.get("degraded", 0),
        })
    except Exception:
        pass
    # Bridge stream/frame metrics from monitoring layer
    try:
        from inference.monitoring.metrics import get_metrics as get_mon
        mon = get_mon().snapshot()
        base.setdefault("stream_start_failures", mon.get("stream_start_failures", 0))
        base.setdefault("latest_frame_updates", mon.get("latest_frame_updates", 0))
    except Exception:
        pass
    # Bridge MJPEG metrics from core metrics
    base.setdefault("active_mjpeg_clients", metrics.active_mjpeg_clients if hasattr(metrics, "active_mjpeg_clients") else 0)
    base.setdefault("mjpeg_frames_served", metrics.mjpeg_frames_served if hasattr(metrics, "mjpeg_frames_served") else 0)
    base.setdefault("stale_camera_frames", metrics.stale_camera_frames if hasattr(metrics, "stale_camera_frames") else 0)
    # Bridge Phase-18 geospatial metrics
    for _geo_key in ("map_state_requests", "map_zone_queries", "map_topology_queries",
                     "geofence_checks", "map_incident_markers", "map_alert_markers"):
        base.setdefault(_geo_key, getattr(metrics, _geo_key, 0))
    return base


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


@router.get("/api/cameras/{camera_id}/latest-frame/image")
def get_camera_latest_frame_image(camera_id: str):
    """Serve the latest annotated frame image with path-traversal protection."""
    from fastapi.responses import FileResponse, JSONResponse
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    from app.core.security import safe_frame_path, is_safe_extension

    frame = get_frame_snapshot_service().get_latest_frame(camera_id)
    if frame.get("status") == "no_frame" or not frame.get("frame_path"):
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "No latest frame available"},
        )

    resolved = safe_frame_path(frame["frame_path"])
    if resolved is None:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "Frame file unavailable"},
        )
    if not is_safe_extension(resolved):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "Unsupported frame file type"},
        )

    media_type = "image/png" if resolved.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(resolved), media_type=media_type)


@router.get("/api/cameras/{camera_id}/latest-frame/annotated-image")
def get_camera_latest_frame_annotated_image(camera_id: str):
    """Serve the latest annotated (bounding-box rendered) frame image."""
    from fastapi.responses import FileResponse, JSONResponse
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    from app.core.security import safe_frame_path, is_safe_extension

    frame = get_frame_snapshot_service().get_latest_frame(camera_id)
    if frame.get("status") == "no_frame":
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "No latest frame available"},
        )

    # Prefer annotated frame; fall back to raw frame
    ann_path = frame.get("annotated_frame_path")
    raw_path = frame.get("frame_path")
    chosen_path = ann_path or raw_path
    if not chosen_path:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "No frame file available"},
        )

    resolved = safe_frame_path(chosen_path)
    if resolved is None:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "Frame file unavailable"},
        )
    if not is_safe_extension(resolved):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "Unsupported frame file type"},
        )
    media_type = "image/png" if resolved.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(resolved), media_type=media_type)


@router.get("/api/cameras/{camera_id}/mjpeg")
async def camera_mjpeg_stream(camera_id: str):
    """Lightweight MJPEG stream using latest frame snapshots (annotated preferred)."""
    import asyncio
    from fastapi.responses import StreamingResponse, JSONResponse
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    from app.core.security import safe_frame_path, is_safe_extension

    # Load streaming config
    try:
        from inference.config_runtime import load_runtime_config
        cfg = load_runtime_config("camera_streaming")
        mjpeg_cfg = cfg.get("mjpeg", {})
        enabled = bool(mjpeg_cfg.get("enabled", True))
        fps = float(mjpeg_cfg.get("fps", 2))
        max_clients = int(mjpeg_cfg.get("max_clients", 16))
        stale_seconds = float(mjpeg_cfg.get("stale_frame_seconds", 10))
    except Exception:
        enabled, fps, max_clients, stale_seconds = True, 2.0, 16, 10.0

    if not enabled:
        return JSONResponse(
            status_code=503,
            content={"status": "disabled", "detail": "MJPEG streaming is disabled"},
        )

    # Check client limit
    current = getattr(metrics, "active_mjpeg_clients", 0)
    if current >= max_clients:
        return JSONResponse(
            status_code=503,
            content={"status": "capacity", "detail": "MJPEG max client limit reached"},
        )

    snapshot_svc = get_frame_snapshot_service()
    interval = max(0.05, 1.0 / fps)
    boundary = b"--aegisframe"

    metrics.increment("active_mjpeg_clients")

    async def generate():
        try:
            while True:
                frame_meta = snapshot_svc.get_latest_frame(camera_id)
                # 17D: prefer annotated frame path when available
                frame_path = frame_meta.get("annotated_frame_path") or frame_meta.get("frame_path")
                age = frame_meta.get("age_seconds")

                img_bytes: bytes | None = None
                if frame_path and (age is None or age <= stale_seconds):
                    resolved = safe_frame_path(frame_path)
                    if resolved is not None and is_safe_extension(resolved):
                        try:
                            with open(str(resolved), "rb") as fh:
                                img_bytes = fh.read()
                        except OSError:
                            img_bytes = None

                if img_bytes:
                    metrics.increment("mjpeg_frames_served")
                    header = (
                        boundary + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(img_bytes)).encode() + b"\r\n"
                        b"\r\n"
                    )
                    yield header + img_bytes + b"\r\n"
                else:
                    # Heartbeat boundary keeps connection alive
                    metrics.increment("stale_camera_frames")
                    yield boundary + b"\r\n\r\n"

                await asyncio.sleep(interval)
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            metrics.increment("mjpeg_client_disconnects")
            with metrics._lock:
                metrics.active_mjpeg_clients = max(0, metrics.active_mjpeg_clients - 1)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=aegisframe",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/cameras/{camera_id}/timeline")
def get_camera_timeline_api(
    camera_id: str,
    start_time: float | None = Query(default=None),
    end_time: float | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return recent timeline entries for a camera, optionally bounded by time range."""
    import time as _time
    try:
        from inference.metrics import metrics as core_metrics
        core_metrics.increment("camera_timeline_queries")
    except Exception:
        pass

    try:
        from inference.forensics.timeline_store import TimelineStore
        store = TimelineStore()
        rows = store.recent(limit=500)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Timeline store unavailable: {exc}")

    filtered = [r for r in rows if r.get("camera_id") == camera_id]
    if start_time is not None:
        filtered = [r for r in filtered if (r.get("timestamp") or 0) >= start_time]
    if end_time is not None:
        filtered = [r for r in filtered if (r.get("timestamp") or 0) <= end_time]
    filtered.sort(key=lambda r: r.get("timestamp", 0))
    items = filtered[-limit:]
    return {"items": items, "count": len(items), "camera_id": camera_id, "status": "ok"}


@router.get("/api/incidents/{incident_id}/replay")
def get_incident_replay_api(incident_id: str):
    """Return a replay manifest for an incident: frames, events, alerts, and timeline."""
    try:
        from inference.metrics import metrics as core_metrics
        core_metrics.increment("incident_replay_queries")
    except Exception:
        pass

    # Load config
    try:
        from inference.config_runtime import load_runtime_config
        rcfg = load_runtime_config("forensic_console").get("incident_replay", {})
        max_frames = int(rcfg.get("max_frames", 500))
        include_alerts = bool(rcfg.get("include_alerts", True))
        include_events = bool(rcfg.get("include_events", True))
        include_timeline = bool(rcfg.get("include_timeline", True))
    except Exception:
        max_frames, include_alerts, include_events, include_timeline = 500, True, True, True

    runtime = get_intelligence_runtime()

    # Resolve incident
    incident = None
    try:
        incident = runtime.incident_engine.get_incident(incident_id)
    except Exception:
        pass
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    inc_dict = incident if isinstance(incident, dict) else (incident.to_dict() if hasattr(incident, "to_dict") else vars(incident))

    # Gather timeline entries containing this incident's track ids
    frames: list[dict] = []
    if include_timeline:
        try:
            from inference.forensics.timeline_store import TimelineStore
            store = TimelineStore()
            all_rows = store.recent(limit=max_frames * 2)
            frames = [
                r for r in all_rows
                if incident_id in (r.get("incident_ids") or [])
            ][:max_frames]
        except Exception:
            pass

    # Gather related alerts
    alert_items: list[dict] = []
    if include_alerts:
        try:
            resp = runtime.get_alerts(limit=200)
            alert_items = [
                a for a in (resp.get("items") or [])
                if incident_id in (a.get("incident_ids") or [])
                or a.get("incident_id") == incident_id
            ]
        except Exception:
            pass

    return {
        "incident_id": incident_id,
        "incident": inc_dict,
        "frames": frames,
        "alerts": alert_items,
        "frame_count": len(frames),
        "alert_count": len(alert_items),
        "status": "ok",
    }


@router.websocket("/ws/frames")
async def websocket_frames_endpoint(websocket: WebSocket):
    """Real-time frame-update WebSocket stream for all cameras."""
    from app.services.websocket_frame_service import get_websocket_frame_service
    await get_websocket_frame_service().handle_connection(websocket)


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


# ── Geospatial / Map endpoints ────────────────────────────────────────────────

def _geo():
    from app.services.geospatial_service import get_geospatial_service
    return get_geospatial_service()


def _geo_metric(name: str) -> None:
    try:
        metrics.increment(name)
    except Exception:
        pass


@router.get("/api/map/state")
def get_map_state_api():
    _geo_metric("map_state_requests")
    state = _geo().get_map_state()
    _geo_metric("map_incident_markers")
    _geo_metric("map_alert_markers")
    return {"item": state, "status": "ok"}


@router.get("/api/map/sites")
def list_map_sites_api():
    items = _geo().list_sites()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/sites/{site_id}")
def get_map_site_api(site_id: str):
    site = _geo().get_site(site_id)
    if site is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")
    return {"item": site, "status": "ok"}


@router.get("/api/map/zones")
def list_map_zones_api(site_id: str | None = Query(default=None)):
    _geo_metric("map_zone_queries")
    items = _geo().list_zones(site_id=site_id)
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/zones/{zone_id}")
def get_map_zone_api(zone_id: str):
    _geo_metric("map_zone_queries")
    zone = _geo().get_zone(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")
    return {"item": zone, "status": "ok"}


@router.get("/api/map/geofences")
def list_map_geofences_api():
    items = _geo().list_geofences()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/cameras")
def list_map_cameras_api():
    items = _geo().get_camera_nodes()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/connections")
def list_map_connections_api():
    items = _geo().get_camera_connections()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/incidents")
def list_map_incidents_api():
    _geo_metric("map_incident_markers")
    items = _geo().get_incident_markers()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/alerts")
def list_map_alerts_api():
    _geo_metric("map_alert_markers")
    items = _geo().get_alert_markers()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/topology")
def get_map_topology_api():
    _geo_metric("map_topology_queries")
    topology = _geo().get_camera_topology()
    return {"item": topology, "status": "ok"}


