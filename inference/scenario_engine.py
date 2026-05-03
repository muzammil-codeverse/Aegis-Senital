from __future__ import annotations
from inference.schemas import DetectionResult

_WEAPONS = frozenset({"knife", "gun", "pistol", "rifle", "sword"})
_VEHICLES = frozenset({"car", "truck", "bus", "motorcycle"})


class SecurityScenario:
    name = "security"

    def evaluate(self, result: DetectionResult) -> list[dict]:
        events = []
        labels = [o.type for o in result.objects]

        weapons = sorted({l for l in labels if l in _WEAPONS})
        if weapons:
            events.append({
                "event_type": "WEAPON_DETECTED",
                "severity": "high",
                "detail": f"Detected: {', '.join(weapons)}",
            })

        person_count = labels.count("person")
        if person_count > 3:
            events.append({
                "event_type": "LOITERING_ALERT",
                "severity": "medium",
                "detail": f"Multiple persons in frame: {person_count}",
            })

        return events


class ClassroomScenario:
    name = "classroom"
    MAX_PERSONS = 35

    def evaluate(self, result: DetectionResult) -> list[dict]:
        events = []
        labels = [o.type for o in result.objects]

        person_count = labels.count("person")
        if person_count > self.MAX_PERSONS:
            events.append({
                "event_type": "OVERCROWDING",
                "severity": "medium",
                "detail": f"Person count {person_count} exceeds limit {self.MAX_PERSONS}",
            })

        if "cell phone" in labels:
            events.append({
                "event_type": "UNAUTHORIZED_DEVICE",
                "severity": "low",
                "detail": "Mobile phone detected in classroom",
            })

        return events


class TrafficScenario:
    name = "traffic"
    PEDESTRIAN_THRESHOLD = 3
    VEHICLE_DENSITY_THRESHOLD = 10

    def evaluate(self, result: DetectionResult) -> list[dict]:
        events = []
        labels = [o.type for o in result.objects]

        if labels.count("person") >= self.PEDESTRIAN_THRESHOLD:
            events.append({
                "event_type": "PEDESTRIAN_ALERT",
                "severity": "medium",
                "detail": f"{labels.count('person')} pedestrians detected",
            })

        vehicle_count = sum(1 for l in labels if l in _VEHICLES)
        if vehicle_count > self.VEHICLE_DENSITY_THRESHOLD:
            events.append({
                "event_type": "HIGH_TRAFFIC_DENSITY",
                "severity": "low",
                "detail": f"Vehicle count: {vehicle_count}",
            })

        return events


_REGISTRY: dict[str, type] = {
    "security": SecurityScenario,
    "classroom": ClassroomScenario,
    "traffic": TrafficScenario,
}

VALID_SCENARIOS: tuple[str, ...] = tuple(_REGISTRY)


def get_scenario(name: str) -> SecurityScenario | ClassroomScenario | TrafficScenario:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown scenario '{name}'. Valid: {VALID_SCENARIOS}")
    return cls()
