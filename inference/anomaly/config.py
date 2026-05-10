from __future__ import annotations
import logging
from functools import lru_cache
from inference.config_runtime import load_runtime_config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_anomaly_config() -> dict:
    try:
        cfg = load_runtime_config("anomaly")
        return cfg.get("anomaly", cfg)
    except Exception as exc:
        logger.warning("Failed to load anomaly config, using defaults: %s", exc)
        return _defaults()


def _defaults() -> dict:
    return {
        "enabled": True,
        "fail_open": True,
        "device": "cuda",
        "temporal_window_seconds": 5,
        "frame_sample_rate": 5,
        "max_tracks_per_window": 100,
        "fusion": {
            "weights": {"rule_engine": 0.40, "video_model": 0.40, "object_context": 0.20},
            "thresholds": {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
        },
        "loitering": {"enabled": True, "min_duration_seconds": 30, "min_track_confidence": 0.55},
        "restricted_zone": {"enabled": True, "min_overlap_ratio": 0.20, "min_duration_seconds": 1.0},
        "abandoned_object": {
            "enabled": True,
            "stationary_seconds": 45,
            "owner_distance_threshold_px": 120,
            "object_classes": ["bag", "backpack", "suitcase", "package"],
        },
        "panic_running": {"enabled": True, "speed_zscore_threshold": 2.5, "min_tracks": 2, "temporal_window_seconds": 5},
        "crowd_anomaly": {"enabled": True, "density_zscore_threshold": 2.5, "min_person_count": 8},
        "violence": {"enabled": True, "require_temporal_confirmation": True, "min_duration_seconds": 2.0},
        "video_model": {"enabled": False, "provider": "pretrained_adapter", "model_path": "models/anomaly/current.pt"},
        "acceptance_policy": {
            "min_auc": 0.90,
            "min_macro_f1": 0.87,
            "min_high_risk_recall": 0.90,
            "max_false_alarms_per_hour": 3,
            "max_p95_latency_ms": 120,
        },
    }
