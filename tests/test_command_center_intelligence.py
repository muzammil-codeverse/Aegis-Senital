from __future__ import annotations

from pathlib import Path

from app.models.uploaded_video_models import UploadedVideoEvent, UploadedVideoReport, UploadedVideoSession, UploadedVideoTimelineItem
from app.services.command_center_intelligence_service import CommandCenterIntelligenceService, SimulationObservationAdapter
from uploaded_video_test_utils import build_case_service, build_incident_repository


def _session(tmp_path: Path) -> UploadedVideoSession:
    report_path = tmp_path / "uploaded_video_results" / "uvs_demo" / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    return UploadedVideoSession(
        session_id="uvs_demo",
        original_filename="demo.avi",
        safe_filename="uploaded_video_uvs_demo.avi",
        storage_uri=str(tmp_path / "uploaded_videos" / "demo.avi"),
        hash_sha256="f" * 64,
        created_by="pytest",
        report_uri=str(report_path),
    )


def _report(session_id: str = "uvs_demo") -> UploadedVideoReport:
    return UploadedVideoReport(
        report_id="uvr_demo",
        session_id=session_id,
        video_metadata={"original_filename": "demo.avi", "frames_processed": 1},
        detections_summary={"total_events": 1, "event_types": {"weapon_detected": 1}},
        chain_of_custody={"source_video": "storage/uploaded_videos/demo.avi"},
    )


def _event() -> UploadedVideoEvent:
    return UploadedVideoEvent(
        event_id="uve_weapon_1",
        session_id="uvs_demo",
        event_type="weapon_detected",
        severity="high",
        risk_score=0.84,
        frame_index=7,
        time_offset_seconds=1.4,
        camera_ids=["uploaded:uvs_demo"],
        track_ids=["trk_7"],
        summary="Possible weapon-related event detected. Operator review required.",
        metadata={"confidence": 0.86, "bounding_box": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}},
    )


def _service(tmp_path: Path) -> CommandCenterIntelligenceService:
    return CommandCenterIntelligenceService(
        storage_dir=tmp_path / "command_center",
        incident_repository=build_incident_repository(tmp_path),
        case_service=build_case_service(tmp_path),
    )


def test_uploaded_detection_converts_to_normalized_event(tmp_path):
    service = _service(tmp_path)
    session = _session(tmp_path)
    event = _event()

    normalized = service.uploaded_video_adapter.normalize(
        session=session,
        report=_report(),
        event=event,
        timeline_item=UploadedVideoTimelineItem(session_id=session.session_id, event_id=event.event_id, title="Weapon"),
        evidence_refs=["uploaded_video:uvs_demo:report"],
    )

    assert normalized.source_type == "uploaded_video"
    assert normalized.source_id == session.session_id
    assert normalized.event_type == "weapon_detected"
    assert normalized.detected_class == "weapon"
    assert normalized.evidence_refs == ["uploaded_video:uvs_demo:report"]


def test_no_detection_report_creates_no_threat_alert(tmp_path):
    service = _service(tmp_path)
    record = service.promote_uploaded_video(
        session=_session(tmp_path),
        report=UploadedVideoReport(session_id="uvs_demo", detections_summary={"total_events": 0}),
        events=[],
        timeline=[],
    )

    assert record.status == "no_detections"
    assert record.alert_ids == []
    assert service.list_alerts() == []


def test_promotion_creates_uploaded_video_alert_and_is_idempotent(tmp_path):
    service = _service(tmp_path)
    session = _session(tmp_path)
    event = _event()
    timeline = [UploadedVideoTimelineItem(session_id=session.session_id, event_id=event.event_id, title="Weapon detected")]

    first = service.promote_uploaded_video(session=session, report=_report(), events=[event], timeline=timeline)
    second = service.promote_uploaded_video(session=session, report=_report(), events=[event], timeline=timeline)

    assert first.alert_ids == second.alert_ids
    assert len(first.alert_ids) == 1
    alert = service.get_alert(first.alert_ids[0])
    assert alert is not None
    assert alert["metadata"]["source_type"] == "uploaded_video"
    assert alert["metadata"]["uploaded_video"]["session_id"] == session.session_id
    assert len(service.list_alerts()) == 1


def test_evidence_manifest_references_uploaded_video_report(tmp_path):
    service = _service(tmp_path)
    session = _session(tmp_path)
    record = service.promote_uploaded_video(session=session, report=_report(), events=[_event()], timeline=[])

    assert f"uploaded_video:{session.session_id}:report" in record.evidence_refs
    manifest_path = Path(session.report_uri).with_name("evidence_manifest.json")
    assert manifest_path.exists()
    assert "system_report" in manifest_path.read_text(encoding="utf-8")


def test_simulation_observation_adapter_maps_to_normalized_event():
    event = SimulationObservationAdapter().normalize_observation(
        {
            "source_type": "simulation_cctv",
            "camera_id": "CAM-BANK-01",
            "scenario_id": "bank_robbery_demo",
            "timestamp": "2026-05-19T10:00:00+00:00",
            "detected_class": "person",
            "event_type": "suspicious_person",
            "confidence": 0.95,
            "metadata": {"zone": "bank_entrance"},
        }
    )

    assert event.source_type == "simulation_cctv"
    assert event.camera_id == "CAM-BANK-01"
    assert event.metadata["simulated"] is True
    assert event.event_type == "suspicious_person"


def test_preflight_style_dry_run_does_not_persist_fake_alerts(tmp_path):
    service = _service(tmp_path)
    record = service.promote_uploaded_video(
        session=_session(tmp_path),
        report=_report(),
        events=[_event()],
        timeline=[],
        dry_run=True,
    )

    assert record.status == "dry_run"
    assert record.alert_ids
    assert service.list_alerts() == []
    assert not list((tmp_path / "command_center" / "uploaded_video_promotions").glob("*.json"))
