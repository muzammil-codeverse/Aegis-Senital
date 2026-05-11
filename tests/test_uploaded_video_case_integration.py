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


def test_uploaded_video_case_creation_attaches_source_and_report(tmp_path, monkeypatch):
    incident_repository = build_incident_repository(tmp_path)
    case_service = build_case_service(tmp_path)
    monkeypatch.setattr(uploaded_video_service_module, "get_incident_repository", lambda: incident_repository)
    monkeypatch.setattr(uploaded_video_service_module, "get_case_service", lambda: case_service)
    monkeypatch.setattr(uploaded_video_service_module, "ModelPool", FakeModelPool)
    monkeypatch.setattr(uploaded_video_service_module, "StreamProcessor", FakeStreamProcessor)
    service = UploadedVideoService(config=uploaded_video_config(tmp_path))
    source_video = create_test_video(tmp_path / "fixtures" / "case.avi")
    session = service.upload_video(build_upload_file(source_video), {}, "operator-1").session

    service._process_session_job(session.session_id, uploaded_video_service_module.threading.Event())
    case = service.create_case_from_session(session.session_id, {}, "operator-1")
    evidence = case_service.list_evidence(case.case_id)
    report = service.get_report(session.session_id)

    assert any(item.evidence_type == "upload" for item in evidence)
    assert any(item.evidence_type == "system_report" for item in evidence)
    assert report is not None
    assert report.model_caveats
