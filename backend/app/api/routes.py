import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.video_service import extract_frames
from app.models.database import SessionLocal, Event, Detection
from app.core.config import load_scenario_config
import json

router = APIRouter()


@router.post("/process-video")
async def process_video(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        raise HTTPException(status_code=400, detail="Unsupported video format")

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        frame_count = extract_frames(tmp_path)
    finally:
        os.unlink(tmp_path)

    return {"frames": frame_count}


@router.get("/config/{scenario}")
def get_config(scenario: str):
    try:
        config = load_scenario_config(scenario)
        return config
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario}' not found")


@router.get("/events")
def list_events():
    db = SessionLocal()
    try:
        events = db.query(Event).order_by(Event.timestamp.desc()).limit(50).all()
        return [{"id": e.id, "timestamp": str(e.timestamp), "type": e.type, "metadata": e.meta} for e in events]
    finally:
        db.close()


@router.get("/detections")
def list_detections():
    db = SessionLocal()
    try:
        detections = db.query(Detection).order_by(Detection.timestamp.desc()).limit(50).all()
        return [{"id": d.id, "timestamp": str(d.timestamp), "type": d.type, "metadata": d.meta} for d in detections]
    finally:
        db.close()
