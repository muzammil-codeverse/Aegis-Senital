from __future__ import annotations
from inference.schemas import DetectionResult

WEAPON_LABELS: frozenset[str] = frozenset({"knife", "gun", "pistol", "rifle", "sword"})
CROWD_THRESHOLD: int = 5


def evaluate(result: DetectionResult) -> dict | None:
    labels = [obj.type for obj in result.objects]

    # Highest priority: weapon detected
    weapons_found = [lbl for lbl in labels if lbl in WEAPON_LABELS]
    if weapons_found:
        return {
            "event_type": "WEAPON_DETECTED",
            "severity": "high",
            "detail": f"Detected: {', '.join(sorted(set(weapons_found)))}",
        }

    # Crowd density
    person_count = labels.count("person")
    if person_count > CROWD_THRESHOLD:
        return {
            "event_type": "CROWD_ALERT",
            "severity": "medium",
            "detail": f"Person count {person_count} exceeds threshold {CROWD_THRESHOLD}",
        }

    return None
