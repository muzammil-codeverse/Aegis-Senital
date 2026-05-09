"""
Phase 25 — Tests for evaluation metric calculations.
"""
from __future__ import annotations

import math
import pytest


class TestDetectionMetrics:

    def test_iou_perfect_overlap(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_iou
        box = [0.0, 0.0, 100.0, 100.0]
        assert compute_iou(box, box) == 1.0

    def test_iou_no_overlap(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_iou
        box1 = [0.0, 0.0, 10.0, 10.0]
        box2 = [20.0, 20.0, 30.0, 30.0]
        assert compute_iou(box1, box2) == 0.0

    def test_iou_partial_overlap(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_iou
        box1 = [0.0, 0.0, 10.0, 10.0]
        box2 = [5.0, 5.0, 15.0, 15.0]
        iou = compute_iou(box1, box2)
        assert 0.0 < iou < 1.0

    def test_ap_perfect_precision(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_ap
        precisions = [1.0] * 11
        recalls = [i / 10 for i in range(11)]
        ap = compute_ap(precisions, recalls)
        assert abs(ap - 1.0) < 0.01

    def test_ap_zero(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_ap
        assert compute_ap([], []) == 0.0

    def test_compute_detection_metrics_empty(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        result = compute_detection_metrics(
            samples=[],
            predictions_by_sample={},
            class_names=["weapon"],
        )
        assert result.warnings  # must warn about empty dataset

    def test_compute_detection_metrics_all_correct(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        samples = [
            {
                "sample_id": "img_001",
                "annotations": [{"class_id": 0, "class_name": "weapon", "bbox_xyxy": [0.0, 0.0, 100.0, 100.0]}],
            }
        ]
        predictions = {
            "img_001": [{"class_id": 0, "score": 0.9, "bbox": [0.0, 0.0, 100.0, 100.0]}]
        }
        result = compute_detection_metrics(samples, predictions, class_names=["weapon"])
        assert result.map_50 is not None
        assert result.map_50 > 0.0
        assert result.precision is not None
        assert result.recall is not None

    def test_match_predictions(self):
        from backend.app.evaluation.metrics.detection_metrics import match_predictions
        predictions = [{"bbox": [0.0, 0.0, 100.0, 100.0], "score": 0.9, "class_id": 0}]
        ground_truth = [{"bbox": [0.0, 0.0, 100.0, 100.0], "class_id": 0}]
        tp_flags, gt_matched = match_predictions(predictions, ground_truth, iou_threshold=0.5)
        assert tp_flags == [True]
        assert gt_matched == [True]


class TestFaceMetrics:

    def test_compute_face_metrics_empty(self):
        from backend.app.evaluation.metrics.face_metrics import compute_face_metrics
        result = compute_face_metrics([])
        assert result.warnings

    def test_compute_face_metrics_perfect(self):
        from backend.app.evaluation.metrics.face_metrics import compute_face_metrics
        pairs = (
            [{"same": True, "similarity": 0.95}] * 100
            + [{"same": False, "similarity": 0.10}] * 100
        )
        result = compute_face_metrics(pairs)
        assert result.recommended_threshold is not None
        assert 0.0 <= result.far <= 1.0
        assert 0.0 <= result.frr <= 1.0
        assert "threshold_recommendation_note" in result.to_dict()

    def test_tar_at_far_thresholds_returned(self):
        from backend.app.evaluation.metrics.face_metrics import compute_face_metrics
        pairs = (
            [{"same": True, "similarity": 0.9}] * 50
            + [{"same": False, "similarity": 0.1}] * 50
        )
        result = compute_face_metrics(pairs, far_thresholds=[1e-1, 1e-2])
        assert "FAR=1e-01" in result.tar_at_far_thresholds
        assert "FAR=1e-02" in result.tar_at_far_thresholds


class TestReIDMetrics:

    def test_compute_reid_metrics_empty(self):
        from backend.app.evaluation.metrics.reid_metrics import compute_reid_metrics
        result = compute_reid_metrics([], [])
        assert result.warnings

    def test_compute_reid_metrics_basic(self):
        from backend.app.evaluation.metrics.reid_metrics import compute_reid_metrics

        def make_emb(identity, val):
            return {"identity_id": identity, "embedding": [val] * 128}

        query = [make_emb("person_1", 1.0)]
        gallery = [
            make_emb("person_1", 0.99),
            make_emb("person_2", -0.99),
        ]
        result = compute_reid_metrics(query, gallery)
        assert result.rank_1 == 1.0

    def test_overlap_detected(self):
        from backend.app.evaluation.metrics.reid_metrics import compute_reid_metrics

        def make_emb(identity, val, path="img.jpg"):
            return {"identity_id": identity, "embedding": [val] * 128, "image_path": path}

        query = [make_emb("p1", 1.0, "img_001.jpg")]
        gallery = [make_emb("p1", 1.0, "img_001.jpg")]
        result = compute_reid_metrics(query, gallery)
        assert result.overlap_or_leakage_detected is True


class TestTrackingMetrics:

    def test_compute_tracking_metrics_empty(self):
        from backend.app.evaluation.metrics.tracking_metrics import compute_tracking_metrics
        result = compute_tracking_metrics({}, {})
        assert result.warnings

    def test_mota_perfect(self):
        from backend.app.evaluation.metrics.tracking_metrics import compute_tracking_metrics
        gt = {1: [{"track_id": 1, "bbox_xywh": [0, 0, 50, 50]}]}
        pred = {1: [{"track_id": 1, "bbox_xywh": [0, 0, 50, 50], "conf": 0.9}]}
        result = compute_tracking_metrics(gt, pred)
        assert result.mota == 1.0

    def test_id_switch_detected(self):
        from backend.app.evaluation.metrics.tracking_metrics import compute_tracking_metrics
        gt = {
            1: [{"track_id": 1, "bbox_xywh": [0, 0, 50, 50]}],
            2: [{"track_id": 1, "bbox_xywh": [0, 0, 50, 50]}],
        }
        pred = {
            1: [{"track_id": 10, "bbox_xywh": [0, 0, 50, 50], "conf": 0.9}],
            2: [{"track_id": 99, "bbox_xywh": [0, 0, 50, 50], "conf": 0.9}],  # ID switch!
        }
        result = compute_tracking_metrics(gt, pred)
        assert result.id_switches is not None
        assert result.id_switches >= 1


class TestLatencyMetrics:

    def test_percentile_empty(self):
        from backend.app.evaluation.metrics.latency_metrics import _percentile
        assert _percentile([], 95) == 0.0

    def test_percentile_single(self):
        from backend.app.evaluation.metrics.latency_metrics import _percentile
        assert _percentile([100.0], 95) == 100.0

    def test_profiler_records_stages(self):
        from backend.app.evaluation.metrics.latency_metrics import LatencyProfiler
        profiler = LatencyProfiler()
        profiler.start()
        profiler.record_stage("yolo_inference", 45.0)
        profiler.record_stage("yolo_inference", 55.0)
        profiler.record_frame()
        result = profiler.compute()
        stage = next((s for s in result.stages if s.stage == "yolo_inference"), None)
        assert stage is not None
        assert stage.avg_ms == 50.0
        assert stage.samples == 2

    def test_profiler_measure_context(self):
        from backend.app.evaluation.metrics.latency_metrics import LatencyProfiler
        import time
        profiler = LatencyProfiler()
        profiler.start()
        with profiler.measure("tracking"):
            time.sleep(0.01)
        result = profiler.compute()
        stage = next((s for s in result.stages if s.stage == "tracking"), None)
        assert stage is not None
        assert stage.samples == 1
        assert stage.avg_ms >= 0.0  # timing resolution varies by OS


class TestGPUMetrics:

    def test_profile_gpu_degrades_gracefully(self):
        from backend.app.evaluation.metrics.gpu_metrics import profile_gpu
        result = profile_gpu()
        # Must not raise even if GPU unavailable
        assert isinstance(result.gpu_available, bool)
        if not result.gpu_available:
            assert result.profiling_degraded is True
            assert result.degradation_reason is not None

    def test_gpu_profile_serializable(self):
        from backend.app.evaluation.metrics.gpu_metrics import profile_gpu
        result = profile_gpu()
        d = result.to_dict()
        import json
        json.dumps(d, default=str)  # must not raise
