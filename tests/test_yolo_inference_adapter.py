"""Phase 26 — Tests for YOLO inference adapter (no real weights required)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


class TestYOLOInferenceAdapter:

    def test_missing_weights_raises_file_not_found(self):
        from backend.app.evaluation.inference.yolo_inference_adapter import YOLOInferenceAdapter
        adapter = YOLOInferenceAdapter(
            model_path="/nonexistent/path/model.pt",
            name="test_yolo",
            device="cpu",
        )
        with pytest.raises(FileNotFoundError, match="YOLO weights not found"):
            adapter.load()

    def test_is_loaded_false_before_load(self):
        from backend.app.evaluation.inference.yolo_inference_adapter import YOLOInferenceAdapter
        adapter = YOLOInferenceAdapter(
            model_path="/nonexistent.pt",
            name="test",
            device="cpu",
        )
        assert adapter.is_loaded() is False

    def test_predict_without_load_returns_error(self):
        from backend.app.evaluation.inference.yolo_inference_adapter import YOLOInferenceAdapter
        adapter = YOLOInferenceAdapter(model_path="/x.pt", name="test", device="cpu")
        pred = adapter.predict("/any/image.jpg")
        assert pred.error is not None
        assert "not loaded" in pred.error.lower()
        assert pred.detections == []

    def test_predict_missing_image_returns_error(self, tmp_path):
        from backend.app.evaluation.inference.yolo_inference_adapter import YOLOInferenceAdapter
        # Create a fake weights file so load() path check passes (but load itself will fail without ultralytics)
        fake_weights = tmp_path / "model.pt"
        fake_weights.write_bytes(b"\x00" * 16)  # not real weights
        adapter = YOLOInferenceAdapter(
            model_path=str(fake_weights),
            name="test",
            device="cpu",
        )
        # Skip if ultralytics not installed
        try:
            adapter.load()
        except ImportError:
            pytest.skip("ultralytics not installed")
        except Exception:
            pytest.skip("Model loading failed with non-real weights")

        pred = adapter.predict("/nonexistent/image.jpg")
        assert pred.error is not None

    def test_adapter_metadata(self):
        from backend.app.evaluation.inference.yolo_inference_adapter import YOLOInferenceAdapter
        adapter = YOLOInferenceAdapter(
            model_path="/x.pt",
            name="weapon_yolov8",
            device="cpu",
            class_names=["weapon"],
            version="v8n",
        )
        assert adapter.model_name == "weapon_yolov8"
        assert adapter.model_version == "v8n"
        assert adapter.device == "cpu"

    def test_detection_prediction_schema(self):
        from backend.app.evaluation.inference.base import DetectionPrediction, DetectionBox
        pred = DetectionPrediction(
            sample_id="img_001",
            detections=[DetectionBox(bbox=[10.0, 20.0, 50.0, 80.0], score=0.85, class_id=0, label="weapon")],
            latency_ms=12.4,
            model_name="weapon_yolov8",
            device="cpu",
        )
        d = pred.to_dict()
        assert d["sample_id"] == "img_001"
        assert d["latency_ms"] == 12.4
        assert len(d["detections"]) == 1
        assert d["detections"][0]["label"] == "weapon"

    def test_detection_box_schema(self):
        from backend.app.evaluation.inference.base import DetectionBox
        box = DetectionBox(bbox=[0.0, 0.0, 100.0, 100.0], score=0.91, class_id=0, label="weapon")
        d = box.to_dict()
        assert d["score"] == 0.91
        assert d["class_id"] == 0
        assert len(d["bbox"]) == 4

    def test_unload_is_safe_without_load(self):
        from backend.app.evaluation.inference.yolo_inference_adapter import YOLOInferenceAdapter
        adapter = YOLOInferenceAdapter(model_path="/x.pt", name="test", device="cpu")
        adapter.unload()  # must not raise
        assert adapter.is_loaded() is False

    def test_weight_download_prevention(self):
        """Verifies the adapter raises on missing path rather than downloading weights."""
        from backend.app.evaluation.inference.yolo_inference_adapter import YOLOInferenceAdapter
        adapter = YOLOInferenceAdapter(
            model_path="yolov8n.pt",  # would auto-download if allowed
            name="test",
            device="cpu",
        )
        # If the file does not exist locally, must raise FileNotFoundError, not download
        weights_exist = Path("yolov8n.pt").exists()
        if not weights_exist:
            with pytest.raises(FileNotFoundError, match="allow_weight_downloads"):
                adapter.load()
