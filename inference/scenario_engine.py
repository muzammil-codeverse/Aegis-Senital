from __future__ import annotations
from inference.schemas import DetectionResult

# Matches configs/weapon.yaml class names + legacy COCO labels for
# backwards-compat with the default yolov8n.pt COCO model.
_WEAPONS: frozenset[str] = frozenset(
    {"pistol", "rifle", "knife", "grenade", "shotgun", "gun", "sword"}
)

# Matches configs/phone.yaml class names + COCO "cell phone".
_DEVICES: frozenset[str] = frozenset({"phone", "tablet", "cell phone"})

_VEHICLES: frozenset[str] = frozenset({"car", "truck", "bus", "motorcycle"})


class SecurityScenario:
    name = "security"

    def evaluate(self, result: DetectionResult) -> list[dict]:
        events: list[dict] = []
        labels = [o.type for o in result.objects]

        weapons = sorted({lbl for lbl in labels if lbl in _WEAPONS})
        if weapons:
            events.append(
                {
                    "event_type": "WEAPON_DETECTED",
                    "severity": "high",
                    "detail": f"Detected: {', '.join(weapons)}",
                }
            )

        person_count = labels.count("person")
        if person_count > 3:
            events.append(
                {
                    "event_type": "LOITERING_ALERT",
                    "severity": "medium",
                    "detail": f"Multiple persons in frame: {person_count}",
                }
            )

        return events


class ClassroomScenario:
    name = "classroom"
    MAX_PERSONS = 35

    def evaluate(self, result: DetectionResult) -> list[dict]:
        events: list[dict] = []
        labels = [o.type for o in result.objects]

        person_count = labels.count("person")
        if person_count > self.MAX_PERSONS:
            events.append(
                {
                    "event_type": "OVERCROWDING",
                    "severity": "medium",
                    "detail": f"Person count {person_count} exceeds limit {self.MAX_PERSONS}",
                }
            )

        # Catches both custom model outputs (phone/tablet) and COCO "cell phone"
        devices_found = sorted({lbl for lbl in labels if lbl in _DEVICES})
        if devices_found:
            events.append(
                {
                    "event_type": "UNAUTHORIZED_DEVICE",
                    "severity": "low",
                    "detail": f"Unauthorized device(s) detected: {', '.join(devices_found)}",
                }
            )

        return events


class TrafficScenario:
    name = "traffic"
    PEDESTRIAN_THRESHOLD = 3
    VEHICLE_DENSITY_THRESHOLD = 10

    def evaluate(self, result: DetectionResult) -> list[dict]:
        events: list[dict] = []
        labels = [o.type for o in result.objects]

        pedestrian_count = labels.count("person")
        if pedestrian_count >= self.PEDESTRIAN_THRESHOLD:
            events.append(
                {
                    "event_type": "PEDESTRIAN_ALERT",
                    "severity": "medium",
                    "detail": f"{pedestrian_count} pedestrians detected",
                }
            )

        vehicle_count = sum(1 for lbl in labels if lbl in _VEHICLES)
        if vehicle_count > self.VEHICLE_DENSITY_THRESHOLD:
            events.append(
                {
                    "event_type": "HIGH_TRAFFIC_DENSITY",
                    "severity": "low",
                    "detail": f"Vehicle count: {vehicle_count}",
                }
            )

        return events


_REGISTRY: dict[str, type] = {
    "security": SecurityScenario,
    "classroom": ClassroomScenario,
    "traffic": TrafficScenario,
}

VALID_SCENARIOS: tuple[str, ...] = tuple(_REGISTRY)


def get_scenario(
    name: str,
) -> SecurityScenario | ClassroomScenario | TrafficScenario:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown scenario '{name}'. Valid: {VALID_SCENARIOS}")
    return cls()
