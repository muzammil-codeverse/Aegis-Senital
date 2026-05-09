from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from app.core.logging_config import logger
from inference.detection_engine import DetectionEngine
from inference.event_buffer import EventBuffer
from inference.event_engine import EventEngine
from inference.identity_db import IdentityDB, get_db
from inference.identity_fusion_engine import IdentityFusionEngine
from inference.model_fusion_engine import ModelFusionEngine
from inference.monitoring.metrics import get_metrics
from inference.runtime import get_intelligence_runtime
from inference.scenario_engine import ScenarioEngine
from inference.schemas import FramePacket
from inference.system_state import record_latency, update_state
from inference.tracker import MultiObjectTracker
from ml.runtime import system_boot_check

FRAME_SKIP = 5
_PIPELINE_WORKERS = 4

_OUTPUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "output")
)

_engine: DetectionEngine | None = None
_fusion_engine: ModelFusionEngine | None = None
_runtime_db: IdentityDB | None = None
_identity_fusion: IdentityFusionEngine | None = None


def _to_legacy_frame_result(packet: FramePacket) -> dict:
    return {
        "timestamp": packet.timestamp,
        "frame_id": packet.frame_id,
        "objects": [
            {
                "type": track.class_name,
                "confidence": track.confidence,
                "bbox": track.bbox,
                "tracking_id": track.track_id,
                "identity_id": track.identity_id,
            }
            for track in packet.tracks
            if track.missed_frames == 0
        ],
    }


def bootstrap_inference_runtime() -> None:
    global _engine, _fusion_engine, _runtime_db, _identity_fusion
    if _engine is not None and _fusion_engine is not None and _runtime_db is not None:
        return

    system_boot_check()
    _engine = DetectionEngine()
    _fusion_engine = ModelFusionEngine()
    _runtime_db = get_db()
    _identity_fusion = IdentityFusionEngine(db=_runtime_db)

    update_state(model_status=_engine.model_status)
    logger.info("Strict inference runtime bootstrapped successfully.")
    logger.info("Identity fusion status: %s", _identity_fusion.get_status())


# ── per-frame worker ──────────────────────────────────────────────────────────

def _process_frame_job(
    frame: np.ndarray,
    frame_index: int,
    scenario: str,
    engine: DetectionEngine,
    fusion_engine: ModelFusionEngine,
    tracker: MultiObjectTracker,
    buffer: EventBuffer,
    event_engine: EventEngine,
    scenario_engine: ScenarioEngine,
    proc_lock: threading.Lock,
) -> dict | None:
    """
    Full per-frame pipeline: detection (parallel) → tracking + events (serialized).

    Detection runs outside proc_lock so multiple workers can overlap their
    GPU/CPU inference calls.  Everything stateful (tracker, buffer, engines)
    is guarded by proc_lock.
    """
    metrics = get_metrics()
    t_pipeline = time.monotonic()

    try:
        resized = cv2.resize(frame, (640, 640))

        # ── Stage 1: detection (CPU/GPU, stateless, runs in parallel) ──────
        t_det = time.monotonic()
        packet = engine.predict(resized, frame_id=frame_index, camera_id=scenario)
        det_ms = (time.monotonic() - t_det) * 1000.0
        record_latency("detection_engine", t_det)

        # ── Stage 2: tracking + events (stateful, serialized) ──────────────
        t_trk = time.monotonic()
        with proc_lock:
            packet.detections = fusion_engine.fuse(
                packet.detections,
                active_tracks=tracker.get_active_tracks(packet.camera_id),
            )
            packet.tracks = tracker.update(packet)
            ts_float = time.time()
            intelligence_runtime = get_intelligence_runtime()
            trajectories = [
                intelligence_runtime.trajectory_engine.update(track, timestamp=ts_float)
                for track in packet.tracks
                if track.missed_frames == 0
            ]
            anomalies = intelligence_runtime.anomaly_engine.evaluate_trajectories(
                trajectories,
                camera_id=packet.camera_id,
                frame_id=packet.frame_id,
                timestamp=ts_float,
            )
            buffer.add(packet)
            frame_events = event_engine.evaluate(buffer)
            frame_scenarios = scenario_engine.aggregate(frame_events)
            intelligence_packet = intelligence_runtime.process_frame_context(
                camera_id=packet.camera_id,
                frame_id=packet.frame_id,
                timestamp=ts_float,
                detections=packet.detections,
                tracks=packet.tracks,
                trajectories=trajectories,
                anomalies=anomalies,
                events=frame_events,
            )

            update_state(
                frames_delta=1,
                active_tracks=len(packet.tracks),
                new_events=frame_events if frame_events else None,
                scene_density=buffer.get_scene_density(),
                latency_ms={"tracking": round((time.monotonic() - t_trk) * 1000.0, 2)},
            )

        # ── Stage 3: annotate + save frame ─────────────────────────────────
        for track in packet.tracks:
            if track.missed_frames > 0:
                continue
            x1, y1, x2, y2 = [int(v) for v in track.bbox]
            label = f"#{track.track_id} {track.class_name} {track.confidence:.2f}"
            cv2.rectangle(resized, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                resized, label, (x1, max(y1 - 5, 0)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
            )

        fname = f"frame_{frame_index:06d}.jpg"
        frame_path = os.path.join(_OUTPUT_DIR, fname)
        cv2.imwrite(frame_path, resized)

        metrics.increment("frames_processed")
        metrics.record_pipeline_time(time.monotonic() - t_pipeline)

        # Update camera registry and frame snapshot
        try:
            from app.services.camera_registry import get_camera_registry
            get_camera_registry().mark_frame_seen(packet.camera_id, timestamp=ts_float)
        except Exception:
            pass
        try:
            from app.services.frame_snapshot_service import get_frame_snapshot_service
            detection_dicts = [
                {"type": t.class_name, "bbox": list(t.bbox), "confidence": t.confidence, "track_id": t.track_id}
                for t in packet.tracks
                if t.missed_frames == 0 and len(t.bbox) == 4
            ]
            get_frame_snapshot_service().update_latest_frame(
                camera_id=packet.camera_id,
                frame_path=fname,
                frame_id=frame_index,
                timestamp=ts_float,
                detections=detection_dicts,
            )
        except Exception:
            pass

        return {
            "frame_result": _to_legacy_frame_result(packet),
            "events": [{**e.to_dict(), "frame_id": frame_index} for e in frame_events],
            "scenarios": [{**s.to_dict(), "frame_id": frame_index} for s in frame_scenarios],
            "intelligence": intelligence_packet,
            "fname": fname,
            "det_ms": round(det_ms, 2),
        }

    except Exception as exc:
        logger.warning("Frame %d processing failed — skipping. Error: %s", frame_index, exc)
        metrics.increment("frames_failed")
        return None


# ── main entry point ──────────────────────────────────────────────────────────

def extract_frames(video_path: str, scenario: str = "security") -> dict:
    bootstrap_inference_runtime()
    if _engine is None or _fusion_engine is None or _runtime_db is None or _identity_fusion is None:
        raise RuntimeError("Inference runtime failed to initialise")

    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_interval_ms = 1000.0 / video_fps

    tracker = MultiObjectTracker(db=_runtime_db, identity_fusion=_identity_fusion)
    buffer = EventBuffer(window=10, min_consecutive=3)
    event_engine = EventEngine(db=_runtime_db)
    scenario_engine = ScenarioEngine(db=_runtime_db)
    proc_lock = threading.Lock()
    metrics = get_metrics()

    logger.info(
        "Video processing started: %s | scenario=%s | fps=%.1f | workers=%d",
        video_path, scenario, video_fps, _PIPELINE_WORKERS,
    )

    frame_index = 0
    futures = []

    try:
        with ThreadPoolExecutor(max_workers=_PIPELINE_WORKERS) as executor:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_index % FRAME_SKIP == 0:
                    # ── Frame drop strategy ────────────────────────────────
                    # If the pipeline is running slower than the video's native
                    # frame interval, skip this sample to prevent queue buildup.
                    avg_ms = metrics.avg_pipeline_time * 1000.0
                    if avg_ms > 0 and avg_ms > frame_interval_ms:
                        logger.debug(
                            "Frame %d skipped — pipeline lag (%.1f ms > %.1f ms interval)",
                            frame_index, avg_ms, frame_interval_ms,
                        )
                        frame_index += 1
                        continue

                    futures.append(
                        executor.submit(
                            _process_frame_job,
                            frame.copy(),
                            frame_index,
                            scenario,
                            _engine,
                            _fusion_engine,
                            tracker,
                            buffer,
                            event_engine,
                            scenario_engine,
                            proc_lock,
                        )
                    )

                frame_index += 1
            # executor.shutdown(wait=True) is called here by the context manager
    finally:
        cap.release()

    # Collect results (all futures are complete at this point)
    frame_results: list[dict] = []
    all_events: list[dict] = []
    confirmed_events: list[dict] = []
    all_scenarios: list[dict] = []
    output_frames: list[str] = []

    for future in futures:
        try:
            result = future.result()
        except Exception as exc:
            logger.warning("Frame future raised unexpectedly: %s", exc)
            continue
        if result is None:
            continue
        frame_results.append(result["frame_result"])
        all_events.extend(result["events"])
        confirmed_events.extend(result["events"])
        all_scenarios.extend(result["scenarios"])
        output_frames.append(result["fname"])

    total_detections = sum(len(r["objects"]) for r in frame_results)
    logger.info(
        "Video processing complete: %d frames, %d sampled, %d detections, "
        "%d events, %d scenarios | avg_pipeline_ms=%.1f",
        frame_index, len(frame_results), total_detections,
        len(all_events), len(all_scenarios),
        metrics.avg_pipeline_time * 1000.0,
    )

    return {
        "scenario": scenario,
        "frames": frame_index,
        "frames_sampled": len(frame_results),
        "detections": frame_results,
        "event_summary": {
            "total": len(all_events),
            "confirmed": len(confirmed_events),
            "high": sum(1 for e in confirmed_events if e.get("severity", "").upper() == "HIGH"),
            "medium": sum(1 for e in confirmed_events if e.get("severity", "").upper() == "MEDIUM"),
            "low": sum(1 for e in confirmed_events if e.get("severity", "").upper() == "LOW"),
            "events": confirmed_events,
        },
        "scenarios": all_scenarios,
        "output_frames": output_frames,
        "metrics": metrics.snapshot(),
    }
