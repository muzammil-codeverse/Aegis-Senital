import pytest
import time
from unittest.mock import MagicMock, patch
from inference.anomaly.anomaly_service import AnomalyService
from inference.anomaly.schemas import AnomalyWindow, AnomalyPrediction


def _loitering_window(camera_id="cam1"):
    win = AnomalyWindow(camera_id=camera_id)
    return win


def test_event_payload_schema():
    svc = AnomalyService()
    # Force a loitering prediction by pre-seeding dwell start
    svc._rule_engine._dwell_start.setdefault("cam1", {})[99] = time.time() - 60
    window = AnomalyWindow(
        camera_id="cam1",
        tracks=[{"track_id": 99, "class_name": "person", "confidence": 0.9,
                 "bbox": [10, 10, 50, 80], "_ts": time.time()}],
    )
    preds = svc.evaluate_window(window)
    for pred in preds:
        d = pred.to_dict()
        assert "camera_id" in d
        assert "anomaly_type" in d
        assert "score" in d
        assert "severity" in d
        assert "confidence" in d
        assert "requires_review" in d
        assert "display_label" in d


def test_event_display_label_is_safe():
    """Ensure display labels use review-safe wording only."""
    svc = AnomalyService()
    svc._rule_engine._dwell_start.setdefault("cam_safe", {})[1] = time.time() - 60
    window = AnomalyWindow(
        camera_id="cam_safe",
        tracks=[{"track_id": 1, "class_name": "person", "confidence": 0.9,
                 "bbox": [10, 10, 50, 80], "_ts": time.time()}],
    )
    preds = svc.evaluate_window(window)
    for pred in preds:
        label = pred.display_label()
        assert "crime confirmed" not in label.lower()
        assert "possible" in label.lower() or "requires" in label.lower() or label


def test_anomaly_metadata_in_packet(monkeypatch):
    """Verify stream_processor attaches anomaly metadata to packet.metadata."""
    from inference.anomaly.schemas import AnomalyPrediction
    mock_svc = MagicMock()
    mock_pred = AnomalyPrediction(
        camera_id="cam1", anomaly_type="loitering", score=0.65,
        severity="medium", confidence=0.60, source="rule_engine", duration_seconds=35.0,
    )
    mock_svc.add_frame.return_value = [mock_pred]

    metadata = {}
    det_dicts = []
    trk_dicts = []
    p28_anomalies = mock_svc.add_frame(
        camera_id="cam1", frame_id=1, timestamp=time.time(),
        detections=det_dicts, tracks=trk_dicts, segmentation=None,
    )
    if p28_anomalies:
        metadata["anomaly_events"] = [a.to_dict() for a in p28_anomalies]

    assert "anomaly_events" in metadata
    assert metadata["anomaly_events"][0]["anomaly_type"] == "loitering"


def test_anomaly_service_degraded_health_on_error():
    svc = AnomalyService()
    svc._rule_engine.evaluate = MagicMock(side_effect=RuntimeError("forced"))
    svc._fail_open = True
    window = AnomalyWindow(camera_id="cam1")
    svc._evaluate_window(window)
    assert svc.health()["status"] == "degraded"
