import time
import pytest
from unittest.mock import patch
from inference.anomaly.rule_engine import RuleEngine
from inference.anomaly.schemas import AnomalyWindow


def _make_window(camera_id="cam1", tracks=None, detections=None):
    return AnomalyWindow(
        camera_id=camera_id,
        tracks=tracks or [],
        detections=detections or [],
    )


def _person_track(tid, speed_vec=(0.0, 0.0), conf=0.9):
    return {
        "track_id": tid,
        "class_name": "person",
        "confidence": conf,
        "bbox": [10, 10, 50, 80],
        "velocity": list(speed_vec),
        "_ts": time.time(),
    }


def test_no_rules_fire_on_empty_window():
    engine = RuleEngine()
    window = _make_window()
    preds = engine.evaluate(window)
    assert preds == []


def test_loitering_rule_fires_after_threshold():
    engine = RuleEngine()
    camera_id = "loiter_cam"
    tid = 42

    # Simulate track appearing for a long time by backdating dwell start
    track = _person_track(tid)
    track["_ts"] = time.time() - 60  # 60 seconds ago
    engine._dwell_start.setdefault(camera_id, {})[tid] = time.time() - 60

    window = _make_window(camera_id=camera_id, tracks=[track])
    preds = engine.evaluate(window)
    loitering = [p for p in preds if p.anomaly_type == "loitering"]
    assert len(loitering) == 1
    assert loitering[0].score > 0.50


def test_loitering_does_not_fire_before_threshold():
    engine = RuleEngine()
    camera_id = "loiter_cam2"
    tid = 43

    track = _person_track(tid)
    engine._dwell_start.setdefault(camera_id, {})[tid] = time.time() - 5  # only 5s

    window = _make_window(camera_id=camera_id, tracks=[track])
    preds = engine.evaluate(window)
    loitering = [p for p in preds if p.anomaly_type == "loitering"]
    assert len(loitering) == 0


def test_panic_running_fires_with_fast_tracks():
    engine = RuleEngine()
    camera_id = "panic_cam"
    # Lower the z-score threshold so the test is config-independent
    engine._cfg.setdefault("panic_running", {})["speed_zscore_threshold"] = 1.0
    engine._cfg["panic_running"]["min_tracks"] = 2
    # 2 fast tracks, 8 near-zero baselines
    tracks = [
        _person_track(1, speed_vec=(100.0, 0.0)),
        _person_track(2, speed_vec=(95.0, 0.0)),
        _person_track(3, speed_vec=(0.5, 0.0)),
        _person_track(4, speed_vec=(0.3, 0.0)),
        _person_track(5, speed_vec=(0.2, 0.0)),
        _person_track(6, speed_vec=(0.4, 0.0)),
        _person_track(7, speed_vec=(0.1, 0.0)),
        _person_track(8, speed_vec=(0.6, 0.0)),
        _person_track(9, speed_vec=(0.2, 0.0)),
        _person_track(10, speed_vec=(0.3, 0.0)),
    ]
    window = _make_window(camera_id=camera_id, tracks=tracks)
    preds = engine.evaluate(window)
    panic = [p for p in preds if p.anomaly_type == "panic_running"]
    assert len(panic) == 1


def test_panic_running_does_not_fire_without_enough_tracks():
    engine = RuleEngine()
    window = _make_window(tracks=[_person_track(1, speed_vec=(200.0, 0.0))])
    preds = engine.evaluate(window)
    panic = [p for p in preds if p.anomaly_type == "panic_running"]
    assert len(panic) == 0


def test_crowd_anomaly_fires_with_many_persons():
    engine = RuleEngine()
    camera_id = "crowd_cam"
    tracks = [_person_track(i) for i in range(15)]  # 15 persons > min_person_count 8
    window = _make_window(camera_id=camera_id, tracks=tracks)
    preds = engine.evaluate(window)
    crowd = [p for p in preds if p.anomaly_type == "crowd_anomaly"]
    assert len(crowd) == 1


def test_abandoned_object_rule():
    engine = RuleEngine()
    camera_id = "aban_cam"
    det = {
        "detection_id": "det1",
        "class": "backpack",
        "bbox": [10, 10, 50, 60],
        "_ts": time.time() - 60,
    }
    # Simulate object being stationary for 60 seconds (threshold is 45)
    engine._stationary.setdefault(camera_id, {})["det1"] = {
        "first_ts": time.time() - 60,
        "bbox": det["bbox"],
    }
    window = _make_window(camera_id=camera_id, detections=[det])
    preds = engine.evaluate(window)
    aban = [p for p in preds if p.anomaly_type == "abandoned_object"]
    assert len(aban) == 1


def test_prediction_requires_review():
    engine = RuleEngine()
    camera_id = "rev_cam"
    engine._dwell_start.setdefault(camera_id, {})[99] = time.time() - 60
    track = _person_track(99)
    window = _make_window(camera_id=camera_id, tracks=[track])
    preds = engine.evaluate(window)
    for p in preds:
        assert p.requires_review is True


def test_no_critical_severity_from_single_weak_frame():
    engine = RuleEngine()
    # Single weak track, just below panic threshold
    window = _make_window(tracks=[_person_track(1, speed_vec=(5.0, 0.0))])
    preds = engine.evaluate(window)
    for p in preds:
        assert p.severity != "critical"
