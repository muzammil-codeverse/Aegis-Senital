from __future__ import annotations

import math
from typing import Any


def _bbox_center(bbox: list[float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox[:4]
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def compute_track_speed(positions: list[tuple[float, float]], timestamps: list[float]) -> float:
    """Pixels per second based on last two recorded positions."""
    if len(positions) < 2 or len(timestamps) < 2:
        return 0.0
    dx = positions[-1][0] - positions[-2][0]
    dy = positions[-1][1] - positions[-2][1]
    dt = max(timestamps[-1] - timestamps[-2], 1e-6)
    return math.hypot(dx, dy) / dt


def compute_acceleration(speeds: list[float], timestamps: list[float]) -> float:
    """Change in speed over time (pixels/s²)."""
    if len(speeds) < 2 or len(timestamps) < 2:
        return 0.0
    dv = speeds[-1] - speeds[-2]
    dt = max(timestamps[-1] - timestamps[-2], 1e-6)
    return dv / dt


def compute_dwell_time(timestamps: list[float]) -> float:
    """Total dwell time in seconds from first to last observation."""
    if len(timestamps) < 2:
        return 0.0
    return timestamps[-1] - timestamps[0]


def compute_direction_change_rate(positions: list[tuple[float, float]]) -> float:
    """
    Rate of significant direction changes (radians per step, averaged).
    Higher values indicate erratic movement.
    """
    if len(positions) < 3:
        return 0.0
    angles = []
    for i in range(1, len(positions) - 1):
        dx1 = positions[i][0] - positions[i - 1][0]
        dy1 = positions[i][1] - positions[i - 1][1]
        dx2 = positions[i + 1][0] - positions[i][0]
        dy2 = positions[i + 1][1] - positions[i][1]
        if math.hypot(dx1, dy1) < 0.5 or math.hypot(dx2, dy2) < 0.5:
            continue
        cos_angle = (dx1 * dx2 + dy1 * dy2) / (
            math.hypot(dx1, dy1) * math.hypot(dx2, dy2)
        )
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angles.append(math.acos(cos_angle))
    return float(sum(angles) / len(angles)) if angles else 0.0


def compute_zone_overlap_duration(
    positions: list[tuple[float, float]],
    timestamps: list[float],
    zone_poly: list[tuple[float, float]],
) -> float:
    """Seconds spent inside a polygon zone (shoelace point-in-polygon)."""
    if not zone_poly or len(positions) < 1:
        return 0.0

    def _in_poly(px: float, py: float) -> bool:
        n = len(zone_poly)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = zone_poly[i]
            xj, yj = zone_poly[j]
            if ((yi > py) != (yj > py)) and px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi:
                inside = not inside
            j = i
        return inside

    total = 0.0
    for i, (pos, ts) in enumerate(zip(positions, timestamps)):
        if _in_poly(pos[0], pos[1]) and i > 0:
            total += ts - timestamps[i - 1]
    return total


def compute_crowd_density(tracks: list[dict], frame_area_px: float = 1.0) -> float:
    """Persons per 1000 px²."""
    persons = [t for t in tracks if t.get("class_name", "").lower() in ("person", "pedestrian")]
    if frame_area_px <= 0:
        return 0.0
    return len(persons) / (frame_area_px / 1000.0)


def compute_nearest_neighbor_distance(
    track_id: Any, tracks: list[dict]
) -> float:
    """Minimum Euclidean distance from this track to any other person track."""
    ref = next((t for t in tracks if t.get("track_id") == track_id), None)
    if ref is None or not ref.get("bbox"):
        return float("inf")
    rc = _bbox_center(ref["bbox"])
    others = [
        t for t in tracks
        if t.get("track_id") != track_id and t.get("class_name", "").lower() in ("person", "pedestrian")
    ]
    if not others:
        return float("inf")
    return min(
        math.hypot(_bbox_center(t["bbox"])[0] - rc[0], _bbox_center(t["bbox"])[1] - rc[1])
        for t in others if t.get("bbox")
    )


def compute_stationary_duration(
    positions: list[tuple[float, float]],
    timestamps: list[float],
    movement_threshold_px: float = 5.0,
) -> float:
    """Seconds object has not moved more than movement_threshold_px from its start."""
    if not positions:
        return 0.0
    origin = positions[0]
    stationary_until = timestamps[0] if timestamps else 0.0
    for pos, ts in zip(positions, timestamps):
        dist = math.hypot(pos[0] - origin[0], pos[1] - origin[1])
        if dist < movement_threshold_px:
            stationary_until = ts
        else:
            break
    return stationary_until - timestamps[0] if timestamps else 0.0


def extract_track_features(
    track: dict,
    track_history: dict[Any, list[dict]],
    all_tracks: list[dict],
    zone_polys: dict[str, list[tuple[float, float]]] | None = None,
    frame_area_px: float = 640.0 * 480.0,
) -> dict:
    """
    Compute all trajectory features for a single track given its history.

    track_history maps track_id -> list of {bbox, timestamp} dicts ordered oldest-first.
    """
    tid = track.get("track_id")
    history = track_history.get(tid, [])

    positions = [_bbox_center(h["bbox"]) for h in history if h.get("bbox")]
    timestamps = [h["timestamp"] for h in history if h.get("timestamp") is not None]

    if len(positions) != len(timestamps):
        n = min(len(positions), len(timestamps))
        positions, timestamps = positions[:n], timestamps[:n]

    speeds: list[float] = []
    for i in range(1, len(positions)):
        dx = positions[i][0] - positions[i - 1][0]
        dy = positions[i][1] - positions[i - 1][1]
        dt = max(timestamps[i] - timestamps[i - 1], 1e-6)
        speeds.append(math.hypot(dx, dy) / dt)

    speed = speeds[-1] if speeds else 0.0
    accel = compute_acceleration(speeds, timestamps) if len(speeds) >= 2 else 0.0
    dwell = compute_dwell_time(timestamps)
    dir_change = compute_direction_change_rate(positions)
    stationary_dur = compute_stationary_duration(positions, timestamps)
    nn_dist = compute_nearest_neighbor_distance(tid, all_tracks)

    zone_durations: dict[str, float] = {}
    if zone_polys:
        for zone_id, poly in zone_polys.items():
            zone_durations[zone_id] = compute_zone_overlap_duration(positions, timestamps, poly)
    max_zone_dur = max(zone_durations.values()) if zone_durations else 0.0

    return {
        "track_id": str(tid),
        "speed_px_per_sec": round(speed, 2),
        "acceleration": round(accel, 2),
        "dwell_seconds": round(dwell, 2),
        "direction_change_rate": round(dir_change, 4),
        "zone_overlap_seconds": round(max_zone_dur, 2),
        "zone_durations": zone_durations,
        "stationary_seconds": round(stationary_dur, 2),
        "nearest_neighbor_px": round(nn_dist, 2) if nn_dist != float("inf") else None,
        "observation_count": len(history),
    }
