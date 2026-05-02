import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.video_service import extract_frames
from app.models.database import SessionLocal, Event, Detection
from app.core.config import load_scenario_config
from app.core.logging_config import logger

router = APIRouter()


@router.post("/process-video")
async def process_video(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        raise HTTPException(status_code=400, detail="Unsupported video format")

    logger.info(f"Received video upload: {file.filename}")
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = extract_frames(tmp_path)
    finally:
        os.unlink(tmp_path)

    logger.info(f"Process-video complete: {result['frames']} frames, {len(result['detections'])} detections")
    return result


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
    db = SessionLocal()
    try:
        events = db.query(Event).order_by(Event.timestamp.desc()).limit(50).all()
        return [{"id": e.id, "timestamp": str(e.timestamp), "type": e.type, "metadata": e.meta} for e in events]
    finally:
        db.close()


@router.get("/detections")
def list_detections():
    logger.info("Detections list requested")
    db = SessionLocal()
    try:
        detections = db.query(Detection).order_by(Detection.timestamp.desc()).limit(50).all()
        return [{"id": d.id, "timestamp": str(d.timestamp), "type": d.type, "metadata": d.meta} for d in detections]
    finally:
        db.close()
