from __future__ import annotations
import math
import threading
import time
from inference.schemas import Track
from inference.monitoring.metrics import get_metrics
from inference.trajectory.trajectory_store import TrajectoryStore, TrajectoryPoint
from inference.trajectory.movement_patterns import detect_behavior
from inference.config_runtime import load_runtime_config


class TrajectoryEngine:
    def __init__(self) -> None:
        cfg = load_runtime_config("trajectory_rules")
        self._fps = float(cfg.get("fps", 30.0))
        self._store = TrajectoryStore(int(cfg.get("history_size", 180)), float(cfg.get("ttl_seconds", 600)))
        self._lock = threading.RLock()

    def update(self, track: Track, timestamp: float | None = None) -> dict:
        now = timestamp or time.time()
        with self._lock:
            self._store.cleanup(now)
            cx = (track.bbox[0] + track.bbox[2]) / 2.0
            cy = (track.bbox[1] + track.bbox[3]) / 2.0
            rec = self._store.get_or_create(track.track_id)
            prev = rec.points[-1] if rec.points else None
            rec.points.append(TrajectoryPoint(cx, cy, now))
            speed = 0.0
            heading = 0.0
            accel = 0.0
            if prev:
                dt = max(1e-3, now - prev.ts)
                dx, dy = cx - prev.x, cy - prev.y
                speed = math.hypot(dx, dy) / dt
                heading = math.atan2(dy, dx)
                rec.velocities.append(speed)
                rec.headings.append(heading)
                if rec.velocities:
                    prev_vel = rec.velocities[-2] if len(rec.velocities) > 1 else speed
                    accel = (speed - prev_vel) / dt
                    rec.accelerations.append(accel)
            rec.last_update = now
            get_metrics().increment("trajectory_updates", 1)
            behavior = detect_behavior(list(rec.headings), list(rec.velocities), list(rec.accelerations))
            return {
                "track_id": track.track_id,
                "camera_id": track.camera_id,
                "identity_id": track.identity_id,
                "point": {"x": cx, "y": cy, "timestamp": now},
                "speed": round(speed, 4),
                "acceleration": round(accel, 4),
                "heading": round(heading, 4),
                "behavior": behavior,
                "path_length": len(rec.points),
            }

    def get_behavior(self, track_id: int) -> dict:
        with self._lock:
            r = self._store.get(track_id)
            if not r:
                return {"label": "unknown", "score": 0.0}
            return detect_behavior(list(r.headings), list(r.velocities), list(r.accelerations))

    def get_path(self, track_id: int) -> list[tuple[float, float, float]]:
        with self._lock:
            r = self._store.get(track_id)
            return [(p.x, p.y, p.ts) for p in r.points] if r else []

    def predict_future_position(self, track_id: int) -> tuple[float, float] | None:
        with self._lock:
            r = self._store.get(track_id)
            if not r or len(r.points) < 2:
                return None
            p1, p2 = r.points[-2], r.points[-1]
            dt = max(1e-3, p2.ts - p1.ts)
            vx, vy = (p2.x - p1.x) / dt, (p2.y - p1.y) / dt
            horizon = 1.0 / self._fps
            return (p2.x + vx * horizon, p2.y + vy * horizon)

    def cleanup(self) -> None:
        with self._lock:
            self._store.cleanup(time.time())

    def get_metrics(self) -> dict:
        with self._lock:
            return {"active_trajectories": len(self._store.items())}
