"""Phase 26 — Tests for mAP@0.5:0.95 multi-threshold computation."""
from __future__ import annotations

import pytest


def _make_sample(sample_id, gt_boxes, class_id=0):
    return {
        "sample_id": sample_id,
        "image_path": f"images/{sample_id}.jpg",
        "annotations": [
            {"class_id": class_id, "bbox_xyxy": box}
            for box in gt_boxes
        ],
    }


def _perfect_pred(sample_id, gt_boxes, class_id=0, score=0.95):
    return [
        {"bbox": box, "score": score, "class_id": class_id}
        for box in gt_boxes
    ]


class TestMapAt50:

    def test_map_50_perfect_detection(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        samples = [_make_sample("s1", [[0, 0, 100, 100]])]
        preds = {"s1": _perfect_pred("s1", [[0, 0, 100, 100]])}
        result = compute_detection_metrics(samples, preds, class_names=["weapon"])
        assert result.map_50 is not None
        assert result.map_50 >= 0.9

    def test_map_50_no_predictions_is_zero(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        samples = [_make_sample("s1", [[0, 0, 100, 100]])]
        result = compute_detection_metrics(samples, {}, class_names=["weapon"])
        assert result.map_50 == 0.0 or result.map_50 is None

    def test_map_50_is_none_when_no_samples(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        result = compute_detection_metrics([], {}, class_names=["weapon"])
        assert result.map_50 is None


class TestMapAt5095:

    def test_map_50_95_computed_when_requested(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        samples = [_make_sample("s1", [[0, 0, 100, 100]])]
        preds = {"s1": _perfect_pred("s1", [[0, 0, 100, 100]])}
        result = compute_detection_metrics(
            samples, preds, class_names=["weapon"], compute_map_50_95=True
        )
        assert result.map_50_95 is not None

    def test_map_50_95_none_when_not_requested(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        samples = [_make_sample("s1", [[0, 0, 100, 100]])]
        preds = {"s1": _perfect_pred("s1", [[0, 0, 100, 100]])}
        result = compute_detection_metrics(samples, preds, class_names=["weapon"])
        assert result.map_50_95 is None

    def test_map_50_95_leq_map_50(self):
        """mAP@0.5:0.95 is always <= mAP@0.5 (tighter criteria reduce AP)."""
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        boxes = [[10, 10, 60, 60]]
        samples = [_make_sample("s1", boxes)]
        preds = {"s1": _perfect_pred("s1", boxes, score=0.9)}
        result = compute_detection_metrics(
            samples, preds, class_names=["weapon"], compute_map_50_95=True
        )
        if result.map_50 is not None and result.map_50_95 is not None:
            assert result.map_50_95 <= result.map_50 + 1e-6

    def test_map_50_95_zero_when_no_matches(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        samples = [_make_sample("s1", [[0, 0, 100, 100]])]
        # Predictions far away from GT — IoU=0 at all thresholds
        preds = {"s1": [{"bbox": [500, 500, 600, 600], "score": 0.9, "class_id": 0}]}
        result = compute_detection_metrics(
            samples, preds, class_names=["weapon"], compute_map_50_95=True
        )
        assert result.map_50_95 == 0.0 or result.map_50_95 is None

    def test_per_class_ap_50_95_populated(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        boxes = [[0, 0, 100, 100]]
        samples = [_make_sample("s1", boxes)]
        preds = {"s1": _perfect_pred("s1", boxes)}
        result = compute_detection_metrics(
            samples, preds, class_names=["weapon"], compute_map_50_95=True
        )
        assert "weapon" in result.per_class_metrics
        # ap_50_95 should be populated
        assert result.per_class_metrics["weapon"]["ap_50_95"] is not None

    def test_per_class_ap_50_present_without_map_50_95(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        boxes = [[0, 0, 50, 50]]
        samples = [_make_sample("s1", boxes)]
        preds = {"s1": _perfect_pred("s1", boxes)}
        result = compute_detection_metrics(samples, preds, class_names=["weapon"])
        assert "weapon" in result.per_class_metrics
        assert "ap_50" in result.per_class_metrics["weapon"]

    def test_multiclass_map_50_95(self):
        from backend.app.evaluation.metrics.detection_metrics import compute_detection_metrics
        samples = [
            _make_sample("s1", [[0, 0, 50, 50]], class_id=0),
            {
                "sample_id": "s2",
                "image_path": "images/s2.jpg",
                "annotations": [{"class_id": 1, "bbox_xyxy": [0, 0, 50, 50]}],
            },
        ]
        preds = {
            "s1": [{"bbox": [0, 0, 50, 50], "score": 0.9, "class_id": 0}],
            "s2": [{"bbox": [0, 0, 50, 50], "score": 0.9, "class_id": 1}],
        }
        result = compute_detection_metrics(
            samples, preds, class_names=["weapon", "phone"], compute_map_50_95=True
        )
        assert result.map_50_95 is not None
        assert "weapon" in result.per_class_metrics
        assert "phone" in result.per_class_metrics
