import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from app.services.video_service import extract_frames
from app.core.config import load_scenario_config
from app.core.logging_config import logger
from inference.identity_db import get_db
from inference.monitoring.metrics import get_metrics

router = APIRouter()

VALID_SCENARIOS = ("security", "classroom", "traffic")


# ── Stream request/response models ────────────────────────────────────────────

class StreamAddRequest(BaseModel):
    source: str
    stream_id: str | None = None


class StreamRemoveRequest(BaseModel):
    stream_id: str


@router.get("/health")
def health_check():
    from app.services.video_service import _engine, _runtime_db, _identity_fusion
    from inference.stream.stream_manager import get_stream_manager

    models_loaded = _engine is not None and getattr(_engine, "is_loaded", False)

    db_connected = False
    if _runtime_db is not None:
        try:
            db_connected = _runtime_db.db_healthy
        except Exception:
            pass

    identity_status: dict = {}
    if _identity_fusion is not None:
        try:
            identity_status = _identity_fusion.get_status()
        except Exception:
            pass

    stream_health = get_stream_manager().health_summary()

    return {
        "status": "ok",
        "models_loaded": models_loaded,
        "db_connected": db_connected,
        "identity_fusion": identity_status,
        "metrics": get_metrics().snapshot(),
        "active_streams": stream_health["active_streams"],
        "total_streams": stream_health["total_streams"],
        "stream_metrics": stream_health["stream_metrics"],
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
