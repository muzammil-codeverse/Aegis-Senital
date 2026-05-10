from __future__ import annotations

import logging
import math
import statistics
import time
from typing import Any

from inference.anomaly.config import load_anomaly_config
from inference.anomaly.schemas import AnomalyWindow, AnomalyPrediction

logger = logging.getLogger(__name__)


def _severity_from_score(score: float, thresholds: dict) -> str:
    if score >= thresholds.get("critical", 0.85):
        return "critical"
    if score >= thresholds.get("high", 0.70):
        return "high"
    if score >= thresholds.get("medium", 0.50):
        return "medium"
    return "low"


class RuleEngine:
    """
    Rule-based temporal anomaly detector.

    All rules require temporal persistence — no critical severity fires from a
    single weak frame. Evidence is collected over the rolling AnomalyWindow.
    """

    def __init__(self) -> None:
        self._cfg = load_anomaly_config()
        self._thresholds = self._cfg.get("fusion", {}).get("thresholds", {
            "low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85,
        })
        # Per-camera track dwell accumulator: {camera_id: {track_id: first_seen_ts}}
        self._dwell_start: dict[str, dict[Any, float]] = {}
        # Per-camera stationary-object registry: {camera_id: {track_id: {first_ts, bbox}}}
        self._stationary: dict[str, dict[Any, dict]] = {}

    def evaluate(self, window: AnomalyWindow) -> list[AnomalyPrediction]:
        predictions: list[AnomalyPrediction] = []
        camera_id = window.camera_id

        if self._cfg.get("loitering", {}).get("enabled", True):
            pred = self._check_loitering(camera_id, window)
            if pred:
                predictions.append(pred)

        if self._cfg.get("restricted_zone", {}).get("enabled", True):
            pred = self._check_restricted_zone(camera_id, window)
            if pred:
                predictions.append(pred)

        if self._cfg.get("abandoned_object", {}).get("enabled", True):
            preds = self._check_abandoned_objects(camera_id, window)
            predictions.extend(preds)

        if self._cfg.get("panic_running", {}).get("enabled", True):
            pred = self._check_panic_running(camera_id, window)
            if pred:
                predictions.append(pred)

        if self._cfg.get("crowd_anomaly", {}).get("enabled", True):
            pred = self._check_crowd_anomaly(camera_id, window)
            if pred:
                predictions.append(pred)

        return predictions

    # ── Loitering ──────────────────────────────────────────────────────────────

    def _check_loitering(self, camera_id: str, window: AnomalyWindow) -> AnomalyPrediction | None:
        cfg = self._cfg.get("loitering", {})
        min_dur = float(cfg.get("min_duration_seconds", 30))
        min_conf = float(cfg.get("min_track_confidence", 0.55))
        now = time.time()

        cam_dwell = self._dwell_start.setdefault(camera_id, {})
        loitering_tracks: list[dict] = []

        for trk in window.tracks:
            tid = trk.get("track_id")
            conf = float(trk.get("confidence", 0.0))
            if conf < min_conf:
                continue
            if tid not in cam_dwell:
                ts = trk.get("_ts", now)
                cam_dwell[tid] = float(ts) if ts else now
            dwell_secs = now - cam_dwell[tid]
            if dwell_secs >= min_dur:
                loitering_tracks.append({"track_id": tid, "dwell_seconds": round(dwell_secs, 1)})

        # Prune departed tracks
        active_ids = {t.get("track_id") for t in window.tracks}
        for tid in list(cam_dwell.keys()):
            if tid not in active_ids:
                del cam_dwell[tid]

        if not loitering_tracks:
            return None

        max_dwell = max(t["dwell_seconds"] for t in loitering_tracks)
        score = min(1.0, 0.50 + (max_dwell - min_dur) / (min_dur * 2))
        return AnomalyPrediction(
            camera_id=camera_id,
            anomaly_type="loitering",
            score=round(score, 4),
            severity=_severity_from_score(score, self._thresholds),
            confidence=round(min(0.90, score), 4),
            source="rule_engine",
            duration_seconds=max_dwell,
            track_ids=[str(t["track_id"]) for t in loitering_tracks],
            evidence={"loitering_tracks": loitering_tracks},
        )

    # ── Restricted zone ────────────────────────────────────────────────────────

    def _check_restricted_zone(
        self, camera_id: str, window: AnomalyWindow
    ) -> AnomalyPrediction | None:
        cfg = self._cfg.get("restricted_zone", {})
        min_overlap = float(cfg.get("min_overlap_ratio", 0.20))
        min_dur = float(cfg.get("min_duration_seconds", 1.0))
        zones = self._cfg.get("zones", {})
        if not zones:
            return None

        violations: list[dict] = []
        for trk in window.tracks:
            bbox = trk.get("bbox")
            if not bbox:
                continue
            for zone_id, zone in zones.items():
                if not zone.get("restricted"):
                    continue
                zbox = zone.get("bbox")
                if not zbox:
                    continue
                overlap = _bbox_overlap_ratio(bbox, zbox)
                if overlap >= min_overlap:
                    dwell = float(trk.get("dwell_seconds", 0.0))
                    if dwell >= min_dur:
                        violations.append({
                            "track_id": trk.get("track_id"),
                            "zone_id": zone_id,
                            "overlap_ratio": round(overlap, 3),
                            "dwell_seconds": round(dwell, 1),
                        })

        if not violations:
            return None

        score = min(1.0, 0.60 + len(violations) * 0.10)
        max_dwell = max(v["dwell_seconds"] for v in violations)
        return AnomalyPrediction(
            camera_id=camera_id,
            anomaly_type="restricted_zone",
            score=round(score, 4),
            severity=_severity_from_score(score, self._thresholds),
            confidence=round(min(0.90, score * 0.9), 4),
            source="rule_engine",
            duration_seconds=max_dwell,
            track_ids=[str(v["track_id"]) for v in violations],
            evidence={"violations": violations},
        )

    # ── Abandoned object ───────────────────────────────────────────────────────

    def _check_abandoned_objects(
        self, camera_id: str, window: AnomalyWindow
    ) -> list[AnomalyPrediction]:
        cfg = self._cfg.get("abandoned_object", {})
        stationary_secs = float(cfg.get("stationary_seconds", 45))
        owner_dist_px = float(cfg.get("owner_distance_threshold_px", 120))
        object_classes = set(cfg.get("object_classes", ["bag", "backpack", "suitcase", "package"]))
        now = time.time()

        cam_stat = self._stationary.setdefault(camera_id, {})
        person_bboxes = [
            t.get("bbox") for t in window.tracks
            if t.get("class_name", "").lower() in ("person", "pedestrian") and t.get("bbox")
        ]
        predictions: list[AnomalyPrediction] = []

        for det in window.detections:
            if det.get("class", "").lower() not in object_classes:
                continue
            did = det.get("detection_id") or det.get("id")
            bbox = det.get("bbox")
            if not bbox:
                continue
            ts = float(det.get("_ts", now))

            if did not in cam_stat:
                cam_stat[did] = {"first_ts": ts, "bbox": bbox}
            stationary_dur = now - cam_stat[did]["first_ts"]

            if stationary_dur < stationary_secs:
                continue

            # Check if an owner is nearby
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            near_owner = any(
                math.hypot((pb[0] + pb[2]) / 2.0 - cx, (pb[1] + pb[3]) / 2.0 - cy) < owner_dist_px
                for pb in person_bboxes if pb
            )
            if near_owner:
                continue

            score = min(1.0, 0.50 + (stationary_dur - stationary_secs) / (stationary_secs * 2))
            predictions.append(AnomalyPrediction(
                camera_id=camera_id,
                anomaly_type="abandoned_object",
                score=round(score, 4),
                severity=_severity_from_score(score, self._thresholds),
                confidence=round(min(0.88, score * 0.95), 4),
                source="rule_engine",
                duration_seconds=round(stationary_dur, 2),
                track_ids=[],
                evidence={
                    "object_class": det.get("class"),
                    "detection_id": str(did),
                    "stationary_seconds": round(stationary_dur, 1),
                },
            ))

        # Evict detections that are no longer present
        active_dids = {
            det.get("detection_id") or det.get("id")
            for det in window.detections
        }
        for did in list(cam_stat.keys()):
            if did not in active_dids:
                del cam_stat[did]

        return predictions

    # ── Panic/running ──────────────────────────────────────────────────────────

    def _check_panic_running(
        self, camera_id: str, window: AnomalyWindow
    ) -> AnomalyPrediction | None:
        cfg = self._cfg.get("panic_running", {})
        z_threshold = float(cfg.get("speed_zscore_threshold", 2.5))
        min_tracks = int(cfg.get("min_tracks", 2))

        person_tracks = [
            t for t in window.tracks
            if t.get("class_name", "").lower() in ("person", "pedestrian")
        ]
        if len(person_tracks) < min_tracks:
            return None

        speeds = [_estimate_speed(t) for t in person_tracks]
        speeds = [s for s in speeds if s is not None]
        if len(speeds) < 2:
            return None

        mu = statistics.mean(speeds)
        sigma = statistics.stdev(speeds) if len(speeds) > 1 else 0.0
        if sigma < 1e-6:
            return None

        fast_tracks = [
            {"track_id": t.get("track_id"), "speed": s}
            for t, s in zip(person_tracks, speeds)
            if (s - mu) / sigma >= z_threshold
        ]
        if len(fast_tracks) < min_tracks:
            return None

        avg_z = statistics.mean((s["speed"] - mu) / sigma for s in fast_tracks)
        score = min(1.0, 0.50 + avg_z * 0.10)
        return AnomalyPrediction(
            camera_id=camera_id,
            anomaly_type="panic_running",
            score=round(score, 4),
            severity=_severity_from_score(score, self._thresholds),
            confidence=round(min(0.85, score * 0.9), 4),
            source="rule_engine",
            duration_seconds=float(self._cfg.get("temporal_window_seconds", 5)),
            track_ids=[str(t["track_id"]) for t in fast_tracks],
            evidence={"fast_tracks": fast_tracks, "population_mean_speed": round(mu, 2)},
        )

    # ── Crowd anomaly ──────────────────────────────────────────────────────────

    def _check_crowd_anomaly(
        self, camera_id: str, window: AnomalyWindow
    ) -> AnomalyPrediction | None:
        cfg = self._cfg.get("crowd_anomaly", {})
        z_threshold = float(cfg.get("density_zscore_threshold", 2.5))
        min_persons = int(cfg.get("min_person_count", 8))

        person_count = sum(
            1 for t in window.tracks
            if t.get("class_name", "").lower() in ("person", "pedestrian")
        )
        if person_count < min_persons:
            return None

        # Approximate density z-score: use person_count as the signal
        # In production the historical baseline would come from a rolling window
        baseline_mean = float(min_persons) * 0.6
        baseline_std = max(1.0, baseline_mean * 0.3)
        z = (person_count - baseline_mean) / baseline_std
        if z < z_threshold:
            return None

        score = min(1.0, 0.45 + z * 0.08)
        return AnomalyPrediction(
            camera_id=camera_id,
            anomaly_type="crowd_anomaly",
            score=round(score, 4),
            severity=_severity_from_score(score, self._thresholds),
            confidence=round(min(0.80, score * 0.85), 4),
            source="rule_engine",
            duration_seconds=float(self._cfg.get("temporal_window_seconds", 5)),
            track_ids=[],
            evidence={"person_count": person_count, "density_zscore": round(z, 2)},
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _bbox_overlap_ratio(a: list[float], b: list[float]) -> float:
    """Intersection-over-min-area overlap ratio."""
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    min_area = min(area_a, area_b)
    return inter / max(min_area, 1e-6)


def _estimate_speed(track: dict) -> float | None:
    velocity = track.get("velocity")
    if velocity and len(velocity) >= 2:
        return math.hypot(velocity[0], velocity[1])
    return None
