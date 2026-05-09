"""Phase 26 — Tests for model selection policy and BenchmarkComparator.recommend()."""
from __future__ import annotations

import pytest


_POLICY = {
    "min_map_50": 0.70,
    "min_recall": 0.65,
    "max_fp_per_image": 0.25,
    "max_p95_latency_ms": 50,
    "max_gpu_memory_mb": 3000,
    "prefer_recall_for_weapon": True,
    "prefer_precision_for_phone": False,
}


class TestModelSelectionPolicy:

    def test_single_passing_model_recommended(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [{"model_name": "good", "map_50": 0.75, "recall": 0.70,
                   "false_positives_per_image": 0.10, "p95_latency_ms": 30}]
        rec = apply_model_selection_policy(models, _POLICY)
        assert rec["recommended_model"] == "good"

    def test_recall_preferred_for_weapon(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [
            {"model_name": "precise", "map_50": 0.80, "recall": 0.67,
             "false_positives_per_image": 0.05, "p95_latency_ms": 20},
            {"model_name": "sensitive", "map_50": 0.74, "recall": 0.82,
             "false_positives_per_image": 0.20, "p95_latency_ms": 25},
        ]
        rec = apply_model_selection_policy(models, _POLICY, task="weapon")
        # prefer_recall_for_weapon: True → sensitive (higher recall)
        assert rec["recommended_model"] == "sensitive"

    def test_below_min_map_50_fails(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [{"model_name": "weak", "map_50": 0.60, "recall": 0.70,
                   "false_positives_per_image": 0.10, "p95_latency_ms": 20}]
        rec = apply_model_selection_policy(models, _POLICY)
        assert rec["recommended_model"] is None

    def test_below_min_recall_fails(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [{"model_name": "low_recall", "map_50": 0.80, "recall": 0.50,
                   "false_positives_per_image": 0.10, "p95_latency_ms": 20}]
        rec = apply_model_selection_policy(models, _POLICY)
        assert rec["recommended_model"] is None

    def test_runner_up_reported(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [
            {"model_name": "best", "map_50": 0.80, "recall": 0.75,
             "false_positives_per_image": 0.10, "p95_latency_ms": 20},
            {"model_name": "second", "map_50": 0.72, "recall": 0.68,
             "false_positives_per_image": 0.12, "p95_latency_ms": 18},
        ]
        rec = apply_model_selection_policy(models, _POLICY, task="weapon")
        assert rec["recommended_model"] is not None
        assert rec["runner_up"] is not None
        assert rec["runner_up"] != rec["recommended_model"]

    def test_policy_failures_contains_all_models(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        models = [
            {"model_name": "a", "map_50": 0.72, "recall": 0.68, "false_positives_per_image": 0.10,
             "p95_latency_ms": 20},
            {"model_name": "b", "map_50": 0.40, "recall": 0.30, "false_positives_per_image": 0.80,
             "p95_latency_ms": 200},
        ]
        rec = apply_model_selection_policy(models, _POLICY)
        assert "a" in rec["policy_failures"]
        assert "b" in rec["policy_failures"]
        assert rec["policy_failures"]["b"]  # b has failures

    def test_comparator_recommend_method(self):
        from backend.app.evaluation.reports.comparison_report import BenchmarkComparator
        comparator = BenchmarkComparator(regression_policy=_POLICY)
        models = [
            {"model_name": "a", "map_50": 0.75, "recall": 0.70, "false_positives_per_image": 0.10,
             "p95_latency_ms": 25, "peak_gpu_mb": 900},
        ]
        rec = comparator.recommend(models, policy=_POLICY, task="weapon")
        assert "recommended_model" in rec

    def test_empty_model_list_returns_none(self):
        from backend.app.evaluation.model_resolver import apply_model_selection_policy
        rec = apply_model_selection_policy([], _POLICY)
        assert rec["recommended_model"] is None
