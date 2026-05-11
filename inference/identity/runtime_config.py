from __future__ import annotations

from copy import deepcopy
from typing import Any

from inference.config_runtime import load_runtime_config


_DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "fail_open": True,
    "face": {
        "enabled": True,
        "provider": "insightface",
        "device": "cuda",
        "detection_size": [640, 640],
        "min_face_size_px": 40,
        "min_detection_score": 0.60,
        "min_quality_score": 0.55,
        "embedding_dim": 512,
        "match_threshold": 0.42,
        "unknown_threshold": 0.35,
    },
    "reid": {
        "enabled": True,
        "provider": "osnet",
        "device": "cuda",
        "min_person_box_area_px": 2500,
        "min_track_length": 5,
        "embedding_dim": 512,
        "match_threshold": 0.55,
    },
    "fusion": {
        "enabled": True,
        "face_weight": 0.65,
        "reid_weight": 0.35,
        "min_fused_confidence": 0.50,
        "identity_ttl_seconds": 600,
        "confidence_decay_seconds": 120,
        "require_face_for_high_confidence": False,
    },
    "liveness": {
        "enabled": False,
        "provider": "pending",
        "fail_if_enabled_missing": True,
    },
    "privacy": {
        "store_raw_faces": False,
        "store_embeddings": True,
        "encrypt_embeddings": False,
        "max_identity_history_days": 30,
    },
    "raw_asset_access": {
        "enabled": False,
        "admin_only": True,
        "audit_all_access": True,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_identity_config() -> dict[str, Any]:
    try:
        payload = load_runtime_config("identity")
    except FileNotFoundError:
        return deepcopy(_DEFAULT_CONFIG)
    root = payload.get("identity", payload)
    if not isinstance(root, dict):
        return deepcopy(_DEFAULT_CONFIG)
    return _deep_merge(_DEFAULT_CONFIG, root)
