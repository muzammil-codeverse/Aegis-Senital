import math
import pytest
from inference.anomaly.trajectory_features import (
    compute_track_speed,
    compute_acceleration,
    compute_dwell_time,
    compute_direction_change_rate,
    compute_stationary_duration,
    compute_nearest_neighbor_distance,
    extract_track_features,
)


def test_speed_calculation():
    positions = [(0.0, 0.0), (30.0, 40.0)]
    timestamps = [0.0, 1.0]
    speed = compute_track_speed(positions, timestamps)
    assert abs(speed - 50.0) < 0.01  # hypot(30, 40) = 50


def test_speed_zero_when_insufficient_data():
    assert compute_track_speed([(0, 0)], [0.0]) == 0.0
    assert compute_track_speed([], []) == 0.0


def test_acceleration():
    speeds = [10.0, 20.0]
    timestamps = [0.0, 1.0]
    accel = compute_acceleration(speeds, timestamps)
    assert abs(accel - 10.0) < 0.01


def test_dwell_time():
    ts = [0.0, 1.0, 5.0, 10.0]
    assert compute_dwell_time(ts) == 10.0
    assert compute_dwell_time([]) == 0.0


def test_direction_change_rate():
    # Straight line → no direction change
    positions = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    rate = compute_direction_change_rate(positions)
    assert rate < 0.01

    # U-turn → large direction change
    positions = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0)]
    rate = compute_direction_change_rate(positions)
    assert rate > 2.5  # close to pi


def test_stationary_duration():
    # Object stays near origin
    positions = [(0.0, 0.0), (1.0, 0.5), (2.0, 1.0), (100.0, 100.0)]
    timestamps = [0.0, 1.0, 2.0, 3.0]
    dur = compute_stationary_duration(positions, timestamps, movement_threshold_px=10.0)
    assert dur >= 2.0


def test_nearest_neighbor():
    tracks = [
        {"track_id": 1, "class_name": "person", "bbox": [0, 0, 10, 10]},
        {"track_id": 2, "class_name": "person", "bbox": [100, 100, 110, 110]},
    ]
    dist = compute_nearest_neighbor_distance(1, tracks)
    assert dist > 100


def test_extract_track_features():
    history = [
        {"bbox": [0, 0, 10, 20], "timestamp": 0.0},
        {"bbox": [5, 5, 15, 25], "timestamp": 1.0},
        {"bbox": [10, 10, 20, 30], "timestamp": 2.0},
    ]
    track = {"track_id": 1, "class_name": "person"}
    track_history = {1: history}
    all_tracks = [{"track_id": 1, "class_name": "person", "bbox": [0, 0, 10, 20]}]
    feats = extract_track_features(track, track_history, all_tracks)
    assert "speed_px_per_sec" in feats
    assert "dwell_seconds" in feats
    assert feats["observation_count"] == 3
