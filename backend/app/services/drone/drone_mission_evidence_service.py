from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.case_models import CaseEvidence
from app.repositories.drone_mission_repository import get_drone_mission_repository
from app.services.case_service import get_case_service


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DroneMissionEvidenceService:
    def __init__(self) -> None:
        self._repo = get_drone_mission_repository()
        self._case_service = get_case_service()

    def build_mission_evidence_bundle(
        self,
        session_id: str,
        *,
        selected_frame_snapshots: list[str] | None = None,
        detection_summary: dict[str, Any] | None = None,
        fusion_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self._repo.get_session(session_id)
        report = self._repo.get_report(session_id)
        telemetry = self._repo.list_telemetry(session_id, limit=5_000)
        events = self._repo.list_events(session_id=session_id, limit=2_000)
        mission = self._repo.get_mission(session.mission_id) if session is not None else None

        route_points = [
            {
                "latitude": point.latitude,
                "longitude": point.longitude,
                "altitude_meters": point.altitude_meters,
                "timestamp": point.timestamp,
            }
            for point in telemetry
            if point.latitude is not None and point.longitude is not None
        ]

        return {
            "generated_at": _now_iso(),
            "session_id": session_id,
            "mission_id": mission.mission_id if mission is not None else None,
            "simulated": True,
            "source_type": "drone_simulation",
            "operator_review_required": True,
            "mission_telemetry_summary": {
                "telemetry_count": len(telemetry),
                "first_timestamp": telemetry[0].timestamp if telemetry else None,
                "last_timestamp": telemetry[-1].timestamp if telemetry else None,
                "status": session.status.value if session is not None else "unknown",
                "progress_percent": session.progress_percent if session is not None else 0.0,
            },
            "selected_frame_snapshots": list(selected_frame_snapshots or []),
            "detection_summary": detection_summary or {
                "events_generated": len(events),
                "event_types": sorted({event.event_type.value for event in events}),
            },
            "mission_route_summary": {
                "waypoints_planned": len(mission.waypoints) if mission is not None else 0,
                "route_points": route_points,
                "simulated_geo": True,
            },
            "fusion_summary": fusion_summary or {
                "candidate_cross_source_observation": bool(events),
                "safe_label": "Candidate cross-source observation",
                "operator_review_required": True,
            },
            "report": report.model_dump(mode="json") if report is not None else None,
        }

    def attach_bundle_to_case(
        self,
        case_id: str,
        session_id: str,
        *,
        actor: str = "operator",
        selected_frame_snapshots: list[str] | None = None,
        detection_summary: dict[str, Any] | None = None,
        fusion_summary: dict[str, Any] | None = None,
    ) -> CaseEvidence:
        bundle = self.build_mission_evidence_bundle(
            session_id,
            selected_frame_snapshots=selected_frame_snapshots,
            detection_summary=detection_summary,
            fusion_summary=fusion_summary,
        )
        evidence = CaseEvidence(
            case_id=case_id,
            evidence_type="system_report",
            title="Simulated drone mission evidence bundle",
            description="Simulated aerial mission summary. Operator review required.",
            source_event_id=session_id,
            storage_uri=None,
            snapshot_uri=None,
            metadata=bundle,
        )
        return self._case_service.store_evidence(
            evidence,
            actor=actor,
            action="evidence_added",
            detail="Simulated drone mission evidence bundle attached.",
            metadata={
                "session_id": session_id,
                "source_type": "drone_simulation",
                "simulated": True,
                "operator_review_required": True,
            },
        )


_service: DroneMissionEvidenceService | None = None


def get_drone_mission_evidence_service() -> DroneMissionEvidenceService:
    global _service
    if _service is None:
        _service = DroneMissionEvidenceService()
    return _service
