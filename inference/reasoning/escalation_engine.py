from __future__ import annotations
from inference.config_runtime import load_runtime_config

def escalation_state(score: float) -> str:
    try:
        cfg = load_runtime_config("escalation_rules").get("thresholds", {})
    except FileNotFoundError:
        cfg = {}
    escalated = float(cfg.get("escalated", 0.85))
    open_threshold = float(cfg.get("open", 0.6))
    if score >= escalated:
        return "ESCALATED"
    if score >= open_threshold:
        return "OPEN"
    return "OPEN"
