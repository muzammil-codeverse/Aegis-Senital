"""
Aegis Sentinel inference package.

The public API remains available through lazy imports so lightweight runtime
modules can be imported without eagerly loading detector, database, or optional
AI dependencies.
"""

from __future__ import annotations

import importlib
from typing import Any

from inference.schemas import (
    Detection,
    DetectionResult,
    DetectedObject,
    Event,
    FramePacket,
    Scenario,
    Track,
    TrackTimeSeries,
)

_LAZY_EXPORTS = {
    "DetectionEngine": ("inference.detection_engine", "DetectionEngine"),
    "CameraGraph": ("inference.camera_graph", "CameraGraph"),
    "IdentityFusionEngine": ("inference.identity_fusion_engine", "IdentityFusionEngine"),
    "MultiObjectTracker": ("inference.tracker", "MultiObjectTracker"),
    "ByteTracker": ("inference.tracker", "ByteTracker"),
    "EventBuffer": ("inference.event_buffer", "EventBuffer"),
    "EventEngine": ("inference.event_engine", "EventEngine"),
    "ScenarioEngine": ("inference.scenario_engine", "ScenarioEngine"),
    "get_scenario": ("inference.scenario_engine", "get_scenario"),
    "ModelFusionEngine": ("inference.model_fusion_engine", "ModelFusionEngine"),
    "PostgresManager": ("inference.db", "PostgresManager"),
    "VectorStore": ("inference.db", "VectorStore"),
    "IdentityDB": ("inference.identity_db", "IdentityDB"),
    "get_db": ("inference.identity_db", "get_db"),
    "insert_track": ("inference.identity_db", "insert_track"),
    "persist_event": ("inference.identity_db", "persist_event"),
    "persist_scenario": ("inference.identity_db", "persist_scenario"),
    "get_active_threats": ("inference.identity_db", "get_active_threats"),
    "SCENARIO_ACTIVE": ("inference.identity_db", "SCENARIO_ACTIVE"),
    "SCENARIO_ESCALATING": ("inference.identity_db", "SCENARIO_ESCALATING"),
    "SCENARIO_RESOLVED": ("inference.identity_db", "SCENARIO_RESOLVED"),
    "SCENARIO_FALSE_ALARM": ("inference.identity_db", "SCENARIO_FALSE_ALARM"),
    "configure_logging": ("inference.logging_setup", "configure_logging"),
    "SystemState": ("inference.system_state", "SystemState"),
    "get_system_snapshot": ("inference.system_state", "get_system_snapshot"),
    "update_state": ("inference.system_state", "update_state"),
    "record_latency": ("inference.system_state", "record_latency"),
    "reset_state": ("inference.system_state", "reset_state"),
}

__all__ = [
    "Detection",
    "Track",
    "TrackTimeSeries",
    "Event",
    "Scenario",
    "FramePacket",
    "DetectedObject",
    "DetectionResult",
    *_LAZY_EXPORTS.keys(),
]


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'inference' has no attribute {name!r}")
    module_name, attr_name = target
    module = importlib.import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
