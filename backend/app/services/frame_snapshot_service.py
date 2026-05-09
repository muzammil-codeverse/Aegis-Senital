from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict

logger = logging.getLogger(__name__)

_MAX_SNAPSHOTS = 256
_SNAPSHOT_TTL = 600.0


def _build_overlay_items(
    detections: list | None,
    tracks: list | None,
    show_confidence: bool = True,
    show_track_id: bool = True,
) -> list[dict]:
    """Convert raw detections/tracks into frontend overlay-ready bbox items."""
    items: list[dict] = []
    seen_bboxes: set = set()

    # Prefer tracks (have track_id) over raw detections
    for t in (tracks or []):
        bbox = t.get("bbox") or t.get("box") or []
        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            continue
        key = tuple(int(v) for v in bbox[:4])
        if key in seen_bboxes:
            continue
        seen_bboxes.add(key)
        label_parts = [str(t.get("type") or t.get("class_name") or "obj")]
        if show_confidence and t.get("confidence") is not None:
            label_parts.append(f"{t['confidence']:.0%}")
        if show_track_id and t.get("track_id") is not None:
            label_parts.append(f"#{t['track_id']}")
        items.append({
            "type": "bbox",
            "label": " ".join(label_parts),
            "confidence": float(t["confidence"]) if t.get("confidence") is not None else None,
            "track_id": t.get("track_id"),
            "severity": t.get("severity"),
            "bbox": [float(v) for v in bbox[:4]],
            "color": None,
        })

    for d in (detections or []):
        bbox = d.get("bbox") or d.get("box") or []
        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            continue
        key = tuple(int(v) for v in bbox[:4])
        if key in seen_bboxes:
            continue
        seen_bboxes.add(key)
        label_parts = [str(d.get("type") or d.get("class_name") or "obj")]
        if show_confidence and d.get("confidence") is not None:
            label_parts.append(f"{d['confidence']:.0%}")
        items.append({
            "type": "bbox",
            "label": " ".join(label_parts),
            "confidence": float(d["confidence"]) if d.get("confidence") is not None else None,
            "track_id": d.get("track_id"),
            "severity": d.get("severity"),
            "bbox": [float(v) for v in bbox[:4]],
            "color": None,
        })

    return items


def _safe_image_url(camera_id: str, frame_path: str | None) -> str | None:
    if not frame_path:
        return None
    return f"/api/cameras/{camera_id}/latest-frame/image"


def _safe_annotated_image_url(camera_id: str, annotated_path: str | None) -> str | None:
    if not annotated_path:
        return None
    return f"/api/cameras/{camera_id}/latest-frame/annotated-image"


def _safe_mjpeg_url(camera_id: str) -> str:
    return f"/api/cameras/{camera_id}/mjpeg"


class FrameSnapshotService:
    def __init__(
        self,
        max_snapshots: int = _MAX_SNAPSHOTS,
        ttl_seconds: float = _SNAPSHOT_TTL,
    ) -> None:
        self._lock = threading.RLock()
        self._frames: OrderedDict[str, dict] = OrderedDict()
        self._max = max_snapshots
        self._ttl = ttl_seconds

    def update_latest_frame(
        self,
        camera_id: str,
        frame_path: str | None = None,
        frame_id: int | None = None,
        timestamp: float | None = None,
        detections: list | None = None,
        tracks: list | None = None,
        events: list | None = None,
        incidents: list | None = None,
        alerts: list | None = None,
        overlays: list | None = None,
        segmentation: dict | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        ts = timestamp or time.time()

        # Build overlay items from tracks+detections
        overlay_items = overlays or _build_overlay_items(detections, tracks)

        # Annotate frame with bounding boxes
        annotated_path: str | None = None
        if frame_path:
            try:
                from app.services.frame_annotation_service import get_frame_annotation_service
                ann_result = get_frame_annotation_service().annotate_for_camera(
                    camera_id=camera_id,
                    input_frame_path=frame_path,
                    overlay_items=overlay_items,
                    frame_id=frame_id,
                    frame_size=(width, height) if width and height else None,
                )
                if ann_result and ann_result.get("annotated_path"):
                    annotated_path = ann_result["annotated_path"]
                    try:
                        from inference.metrics import metrics as core_metrics
                        core_metrics.increment("annotated_frames_generated")
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("Frame annotation failed for %s: %s", camera_id, exc)
                try:
                    from inference.metrics import metrics as core_metrics
                    core_metrics.increment("annotation_failures")
                except Exception:
                    pass

        record = {
            "camera_id": camera_id,
            "frame_path": frame_path,
            "annotated_frame_path": annotated_path,
            "frame_id": frame_id,
            "timestamp": ts,
            "detections": detections or [],
            "tracks": tracks or [],
            "events": events or [],
            "incidents": incidents or [],
            "alerts": alerts or [],
            "segmentation": segmentation,
            "overlays": overlay_items,
            "overlay_items": overlay_items,
            "width": width,
            "height": height,
            "image_url": _safe_image_url(camera_id, frame_path),
            "annotated_image_url": _safe_annotated_image_url(camera_id, annotated_path),
            "mjpeg_url": _safe_mjpeg_url(camera_id),
            "updated_at": ts,
        }

        # Broadcast to WebSocket frame clients
        try:
            from app.services.websocket_frame_service import get_websocket_frame_service
            get_websocket_frame_service().broadcast_frame_update(
                camera_id=camera_id,
                frame_id=frame_id,
                timestamp=ts,
                image_url=record["image_url"],
                annotated_image_url=record["annotated_image_url"],
                mjpeg_url=record["mjpeg_url"],
                overlay_count=len(overlay_items),
                stale=False,
            )
        except Exception:
            pass

        with self._lock:
            self._evict_expired(ts)
            if len(self._frames) >= self._max and camera_id not in self._frames:
                self._frames.popitem(last=False)
            self._frames[camera_id] = record
            self._frames.move_to_end(camera_id)

        # Update camera registry frame timestamp
        try:
            from app.services.camera_registry import get_camera_registry
            get_camera_registry().mark_frame_seen(camera_id, timestamp=ts)
        except Exception:
            pass
        # Update metrics
        try:
            from inference.monitoring.metrics import get_metrics
            get_metrics().increment("latest_frame_updates")
        except Exception:
            pass
        try:
            from inference.metrics import metrics as core_metrics
            core_metrics.increment("latest_frame_updates")
        except Exception:
            pass

    def get_latest_frame(self, camera_id: str) -> dict:
        now = time.time()
        with self._lock:
            frame = self._frames.get(camera_id)
        if frame is None:
            return {
                "camera_id": camera_id,
                "frame_path": None,
                "annotated_frame_path": None,
                "frame_id": None,
                "timestamp": None,
                "detections": [],
                "tracks": [],
                "events": [],
                "incidents": [],
                "alerts": [],
                "segmentation": None,
                "overlays": [],
                "overlay_items": [],
                "width": None,
                "height": None,
                "image_url": None,
                "annotated_image_url": None,
                "mjpeg_url": _safe_mjpeg_url(camera_id),
                "updated_at": None,
                "stale": True,
                "age_seconds": None,
                "status": "no_frame",
            }
        ts = float(frame.get("timestamp") or 0)
        age = now - ts if ts else None
        stale = age is None or age > _SNAPSHOT_TTL
        return {
            **frame,
            "stale": stale,
            "age_seconds": round(age, 1) if age is not None else None,
            "status": "ok",
        }

    def list_latest_frames(self) -> list[dict]:
        now = time.time()
        with self._lock:
            frames = list(self._frames.values())
        result = []
        for f in frames:
            ts = float(f.get("timestamp") or 0)
            age = now - ts if ts else None
            stale = age is None or age > _SNAPSHOT_TTL
            if not stale:
                result.append({
                    **f,
                    "stale": stale,
                    "age_seconds": round(age, 1) if age is not None else None,
                    "status": "ok",
                })
        return result

    def _evict_expired(self, now: float) -> None:
        expired = [
            cid for cid, f in self._frames.items()
            if now - float(f.get("timestamp") or 0) > self._ttl
        ]
        for cid in expired:
            del self._frames[cid]


_snapshot_service: FrameSnapshotService | None = None
_snapshot_service_lock = threading.Lock()


def get_frame_snapshot_service() -> FrameSnapshotService:
    global _snapshot_service
    if _snapshot_service is None:
        with _snapshot_service_lock:
            if _snapshot_service is None:
                _snapshot_service = FrameSnapshotService()
    return _snapshot_service
