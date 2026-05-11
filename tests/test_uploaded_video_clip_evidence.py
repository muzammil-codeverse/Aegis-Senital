from __future__ import annotations

import hashlib

from app.models.uploaded_video_models import (
    UploadedVideoCaseCreationRequest,
    UploadedVideoEvent,
    UploadedVideoReplayClipMetadata,
    UploadedVideoReport,
    UploadedVideoSession,
    UploadedVideoProgress,
)
from app.services import uploaded_video_service as uploaded_video_service_module
from app.services.uploaded_video_service import UploadedVideoService
from uploaded_video_test_utils import build_case_service, build_incident_repository, uploaded_video_config


def test_create_case_attaches_clip_evidence(tmp_path, monkeypatch):
    incident_repository = build_incident_repository(tmp_path)
    case_service = build_case_service(tmp_path)
    monkeypatch.setattr(uploaded_video_service_module, "get_incident_repository", lambda: incident_repository)
    monkeypatch.setattr(uploaded_video_service_module, "get_case_service", lambda: case_service)

    cfg = uploaded_video_config(tmp_path)
    cfg["uploaded_video"]["replay"] = {"enabled": False}
    service = UploadedVideoService(config=cfg)

    session = UploadedVideoSession(
        session_id="uvs_testclipsess01",
        original_filename="f.avi",
        safe_filename="f.avi",
        storage_uri="storage/x.mp4",
        hash_sha256="bb" * 32,
        duration_seconds=10.0,
        frame_count=10,
        fps=5.0,
        status="completed",
        progress=UploadedVideoProgress(frames_processed=10, total_frames=10, percent=100.0),
        created_by="u1",
    )
    service._write_session(session)

    clips_dir = service._session_dir(session.session_id) / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_path = clips_dir / "evt_clip.mp4"
    clip_path.write_bytes(b"clip-bytes")
    clip_digest = hashlib.sha256(b"clip-bytes").hexdigest()

    clip = UploadedVideoReplayClipMetadata(
        clip_id="uvclip_1",
        session_id=session.session_id,
        event_id="evt_clip",
        start_time_seconds=0.0,
        end_time_seconds=2.0,
        duration_seconds=2.0,
        storage_uri=service._storage_uri(clip_path),
        hash_sha256=clip_digest,
        size_bytes=len(b"clip-bytes"),
    )

    event = UploadedVideoEvent(
        event_id="evt_clip",
        session_id=session.session_id,
        event_type="motion",
        summary="s",
        replay_clip=clip,
    )
    service._write_json(service._events_path(session.session_id), [event.model_dump(mode="json")])
    service._write_json(service._timeline_path(session.session_id), [])
    report_path = service._report_path(session.session_id)
    service._write_json(
        report_path,
        UploadedVideoReport(
            session_id=session.session_id,
            generated_by="u1",
            replay_clips=[clip.model_dump(mode="json")],
            replay_summary={"clips_generated": 1, "events_total": 1, "events_with_clips": 1, "events_without_clips": 0},
        ).model_dump(mode="json"),
    )

    case = service.create_case_from_session(
        session.session_id,
        UploadedVideoCaseCreationRequest(
            attach_source_video=False,
            attach_snapshots=False,
            attach_report=False,
            attach_replay_clips=True,
        ),
        "u1",
    )
    evidence = case_service.list_evidence(case.case_id)
    types = {e.evidence_type for e in evidence}
    assert "clip" in types
    clip_items = [e for e in evidence if e.evidence_type == "clip"]
    assert clip_items[0].hash_sha256 == clip.hash_sha256
    assert "Possible incident" in (clip_items[0].description or "")
    assert clip_items[0].source_event_id == "evt_clip"
