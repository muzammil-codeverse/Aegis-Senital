from app.models.uploaded_video_models import UploadedVideoCaseCreationRequest
from app.services import uploaded_video_service as uploaded_video_service_module
from app.services.uploaded_video_service import UploadedVideoService
from uploaded_video_test_utils import (
    FakeModelPool,
    FakeStreamProcessor,
    build_case_service,
    build_incident_repository,
    build_upload_file,
    create_test_video,
    uploaded_video_config,
)


def test_uploaded_video_service_upload_process_and_case_creation(tmp_path, monkeypatch):
    incident_repository = build_incident_repository(tmp_path)
    case_service = build_case_service(tmp_path)
    monkeypatch.setattr(uploaded_video_service_module, "get_incident_repository", lambda: incident_repository)
    monkeypatch.setattr(uploaded_video_service_module, "get_case_service", lambda: case_service)
    monkeypatch.setattr(uploaded_video_service_module, "ModelPool", FakeModelPool)
    monkeypatch.setattr(uploaded_video_service_module, "StreamProcessor", FakeStreamProcessor)

    service = UploadedVideoService(config=uploaded_video_config(tmp_path))
    source_video = create_test_video(tmp_path / "fixtures" / "demo.avi")
    upload = service.upload_video(build_upload_file(source_video), {}, "operator-1")

    assert upload.session.hash_sha256
    service._process_session_job(upload.session.session_id, uploaded_video_service_module.threading.Event())
    status = service.get_status(upload.session.session_id)
    events = service.get_events(upload.session.session_id)
    report = service.get_report(upload.session.session_id)

    assert status.status == "completed"
    assert status.progress.frames_processed > 0
    assert events
    assert report is not None
    assert report.model_caveats
    assert incident_repository.list_session_events(upload.session.session_id)

    created = service.create_case_from_session(
        upload.session.session_id,
        UploadedVideoCaseCreationRequest(title="Uploaded session case"),
        "operator-1",
    )
    evidence = case_service.list_evidence(created.case_id)

    assert created.case_id
    assert evidence
