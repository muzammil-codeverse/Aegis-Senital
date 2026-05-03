from __future__ import annotations
from inference.schemas import DetectionResult

# Matches configs/weapon.yaml class names + legacy COCO knife/gun labels for
# backwards-compat with the default yolov8n.pt COCO model.
WEAPON_LABELS: frozenset[str] = frozenset(
    {"pistol", "rifle", "knife", "grenade", "shotgun", "gun", "sword"}
)

# Matches configs/phone.yaml class names + COCO "cell phone" label.
DEVICE_LABELS: frozenset[str] = frozenset({"phone", "tablet", "cell phone"})

CROWD_THRESHOLD: int = 5


def evaluate(result: DetectionResult) -> dict | None:
    labels = [obj.type for obj in result.objects]

    weapons_found = sorted({lbl for lbl in labels if lbl in WEAPON_LABELS})
    if weapons_found:
        return {
            "event_type": "WEAPON_DETECTED",
            "severity": "high",
            "detail": f"Detected: {', '.join(weapons_found)}",
        }

    person_count = labels.count("person")
    if person_count > CROWD_THRESHOLD:
        return {
            "event_type": "CROWD_ALERT",
            "severity": "medium",
            "detail": f"Person count {person_count} exceeds threshold {CROWD_THRESHOLD}",
        }

    return None
