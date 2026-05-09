"""Phase 26 — Tests for model resolver and model selection policy."""
from __future__ import annotations

import pytest


class TestResolveAdapter:

    def test_missing_required_model_raises(self):
        from backend.app.evaluation.model_resolver import resolve_adapter
        cfg = {
            "name": "weapon_yolov8_baseline",
            "backend": "ultralytics_yolo",
            "path": "/nonexistent/path/model.pt",
            "required": True,
        }
        with pytest.raises(FileNotFoundError):
            resolve_adapter(cfg, device="cpu")

    def test_missing_optional_model_returns_none(self):
        from backend.app.evaluation.model_resolver import resolve_adapter
        cfg = {
            "name": "weapon_yolo11_candidate",
            "backend": "ultralytics_yolo",
            "path": "/nonexistent/path/model.pt",
            "required": False,
        }
        result = resolve_adapter(cfg, device="cpu", allow_missing=True)
        assert result is None

    def test_unsupported_backend_raises(self):
        from backend.app.evaluation.model_resolver import resolve_adapter
        cfg = {"name": "bad_model", "backend": "tensorrt_custom", "path": "x.pt", "required": False}
        with pytest.raises(ValueError, match="Unsupported model backend"):
            resolve_adapter(cfg, device="cpu")

    def test_resolve_candidates_no_config_yields_nothing(self):
        from backend.app.evaluation.model_resolver import resolve_candidates
        results = list(resolve_candidates({}, task="weapon", device="cpu"))
        assert results == []

    def test_resolve_candidates_optional_missing_yields_none(self):
        from backend.app.evaluation.model_resolver import resolve_candidates
        config = {
            "model_candidates": {
                "weapon": [
                    {"name": "candidate_a", "backend": "ultralytics_yolo",
                     "path": "/nonexistent.pt", "required": False},
                ]
            }
        }
        results = list(resolve_candidates(config, task="weapon", device="cpu"))
        assert len(results) == 1
        cfg, adapter = results[0]
        assert cfg["name"] == "candidate_a"
        assert adapter is None

    def test_resolve_candidates_required_missing_raises(self):
        from backend.app.evaluation.model_resolver import resolve_candidates
        config = {
            "model_candidates": {
                "weapon": [
                    {"name": "baseline", "backend": "ultralytics_yolo",
                     "path": "/nonexistent.pt", "required": True},
                ]
            }
        }
        with pytest.raises(FileNotFoundError):
            list(resolve_candidates(config, task="weapon", device="cpu"))


class TestApplyModelSelectionPolicy:

    def _policy(self):
        return {
            "min_map_50": 0.70,
            "min_recall": 0.65,
            "max_fp_per_image": 0.25,
            "max_p95_latency_ms": 50,
            "max_gpu_memory_mb": 3000,
            "prefer_recall_for_weapon": True,
        }

    def test_best_model_selected_by_recall(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [
            {"model_name": "baseline", "map_50": 0.72, "recall": 0.66,
             "false_positives_per_image": 0.18, "p95_latency_ms": 20, "peak_gpu_mb": 900},
            {"model_name": "candidate", "map_50": 0.76, "recall": 0.71,
             "false_positives_per_image": 0.15, "p95_latency_ms": 25, "peak_gpu_mb": 950},
        ]
        rec = apply_model_selection_policy(models, self._policy(), task="weapon")
        assert rec["recommended_model"] == "candidate"
        assert rec["confidence"] in ("high", "medium")

    def test_high_latency_model_fails_policy(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [
            {"model_name": "fast", "map_50": 0.72, "recall": 0.68,
             "false_positives_per_image": 0.10, "p95_latency_ms": 30, "peak_gpu_mb": 800},
            {"model_name": "slow", "map_50": 0.80, "recall": 0.75,
             "false_positives_per_image": 0.10, "p95_latency_ms": 120, "peak_gpu_mb": 900},
        ]
        rec = apply_model_selection_policy(models, self._policy(), task="weapon")
        # slow violates latency — fast should be recommended
        assert rec["recommended_model"] == "fast"
        assert "slow" in rec["policy_failures"]
        assert rec["policy_failures"]["slow"]

    def test_no_model_passes_policy_returns_none(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [
            {"model_name": "bad_a", "map_50": 0.50, "recall": 0.40,
             "false_positives_per_image": 0.50, "p95_latency_ms": 200},
        ]
        rec = apply_model_selection_policy(models, self._policy(), task="weapon")
        assert rec["recommended_model"] is None
        assert rec["confidence"] == "low"

    def test_fp_over_limit_fails_policy(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [
            {"model_name": "high_fp", "map_50": 0.75, "recall": 0.70,
             "false_positives_per_image": 0.80, "p95_latency_ms": 20},
        ]
        rec = apply_model_selection_policy(models, self._policy())
        assert rec["recommended_model"] is None

    def test_gpu_over_limit_fails_policy(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [
            {"model_name": "gpu_hog", "map_50": 0.75, "recall": 0.70,
             "false_positives_per_image": 0.10, "p95_latency_ms": 20, "peak_gpu_mb": 8000},
        ]
        rec = apply_model_selection_policy(models, self._policy())
        assert rec["recommended_model"] is None
        failures = rec["policy_failures"].get("gpu_hog", [])
        assert any("GPU" in f for f in failures)
