from __future__ import annotations

def escalation_state(score: float) -> str:
    if score >= 0.85:
        return "ESCALATED"
    if score >= 0.6:
        return "OPEN"
    return "OPEN"
