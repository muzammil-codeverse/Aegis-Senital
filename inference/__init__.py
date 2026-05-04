"""
Aegis Sentinel — real-time temporal surveillance intelligence layer.

Public API (Phase 6–10 hardened + Phase 8–9 persistence layer):

    Types
    -----
    Detection         single YOLO model output, normalized class name
    Track             persistent cross-frame identity with velocity + stability
                      + persistent_track_id (DB-backed cross-session UUID)
    TrackTimeSeries   per-track time-series store (confidence, bbox, threat score)
    Event             scored threat event with severity_score in [0, 1]
    Scenario          cluster-derived scenario with narrative, lifecycle status
    FramePacket       per-frame data bundle flowing through the pipeline

    Engines
    -------
    DetectionEngine      dual-model YOLO inference -> FramePacket
    MultiObjectTracker   hybrid (IoU + motion + ReID) tracker + DB sync
    EventBuffer          time-series context window with noise suppression
    EventEngine          continuous threat scoring + automatic event persistence
    ScenarioEngine       union-find cluster + lifecycle state management
    ModelFusionEngine    multi-model conflict resolution (weapon vs phone)
    IdentityFusionEngine face + appearance embedding identity resolver
    CameraGraph          cross-camera transition graph

    Persistence
    -----------
    IdentityDB           Postgres/FAISS-backed tracks/events/scenarios adapter
    get_db               process-wide IdentityDB singleton
    insert_track         convenience wrapper
    persist_event        convenience wrapper
    persist_scenario     convenience wrapper
    get_active_threats   convenience wrapper
    SCENARIO_ACTIVE / ESCALATING / RESOLVED / FALSE_ALARM  lifecycle constants

    Logging
    -------
    configure_logging    wire up logs/inference.log + events.log + system_health.log

    Observability
    -------------
    SystemState          runtime telemetry dataclass
    get_system_snapshot  thread-safe analytics snapshot
    update_state         incremental state update
    record_latency       per-module latency helper

    Legacy API (backwards compatible with backend/video_service.py)
    ---------------------------------------------------------------
    DetectedObject, DetectionResult   legacy schema types
    ByteTracker                       legacy tracker class, disabled in production
    get_scenario                      security/classroom/traffic factory
"""

from inference.schemas import (
    Detection,
    Track,
    TrackTimeSeries,
    Event,
    Scenario,
    FramePacket,
    DetectedObject,
    DetectionResult,
)
from inference.detection_engine import DetectionEngine
from inference.camera_graph import CameraGraph
from inference.identity_fusion_engine import IdentityFusionEngine
from inference.tracker import MultiObjectTracker, ByteTracker
from inference.event_buffer import EventBuffer
from inference.event_engine import EventEngine
from inference.scenario_engine import ScenarioEngine, get_scenario
from inference.model_fusion_engine import ModelFusionEngine
from inference.db import PostgresManager, VectorStore
from inference.identity_db import (
    IdentityDB,
    get_db,
    insert_track,
    persist_event,
    persist_scenario,
    get_active_threats,
    SCENARIO_ACTIVE,
    SCENARIO_ESCALATING,
    SCENARIO_RESOLVED,
    SCENARIO_FALSE_ALARM,
)
from inference.logging_setup import configure_logging
from inference.system_state import (
    SystemState,
    get_system_snapshot,
    update_state,
    record_latency,
    reset_state,
)

__all__ = [
    # Phase 6–10 types
    "Detection",
    "Track",
    "TrackTimeSeries",
    "Event",
    "Scenario",
    "FramePacket",
    # Phase 6–10 engines
    "DetectionEngine",
    "CameraGraph",
    "IdentityFusionEngine",
    "MultiObjectTracker",
    "EventBuffer",
    "EventEngine",
    "ScenarioEngine",
    # Phase 8–9 additions
    "ModelFusionEngine",
    "PostgresManager",
    "VectorStore",
    "IdentityDB",
    "get_db",
    "insert_track",
    "persist_event",
    "persist_scenario",
    "get_active_threats",
    "SCENARIO_ACTIVE",
    "SCENARIO_ESCALATING",
    "SCENARIO_RESOLVED",
    "SCENARIO_FALSE_ALARM",
    "configure_logging",
    # Observability
    "SystemState",
    "get_system_snapshot",
    "update_state",
    "record_latency",
    "reset_state",
    # Legacy compatibility
    "DetectedObject",
    "DetectionResult",
    "ByteTracker",
    "get_scenario",
]
