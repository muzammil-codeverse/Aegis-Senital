from app.repositories.incident_repository import JsonlIncidentRepository
from app.services import uploaded_video_service as uploaded_video_service_module
from app.services.uploaded_video_service import UploadedVideoService
from uploaded_video_test_utils import (
    FakeModelPool,
    FakeStreamProcessor,
    build_case_service,
    build_upload_file,
    create_test_video,
    uploaded_video_config,
)


def test_uploaded_video_processing_persists_events_across_repository_reloads(tmp_path, monkeypatch):
    incident_repository = JsonlIncidentRepository(str(tmp_path / "incidents"))
    monkeypatch.setattr(uploaded_video_service_module, "get_incident_repository", lambda: incident_repository)
    monkeypatch.setattr(uploaded_video_service_module, "get_case_service", lambda: build_case_service(tmp_path))
    monkeypatch.setattr(uploaded_video_service_module, "ModelPool", FakeModelPool)
    monkeypatch.setattr(uploaded_video_service_module, "StreamProcessor", FakeStreamProcessor)
    service = UploadedVideoService(config=uploaded_video_config(tmp_path))
    source_video = create_test_video(tmp_path / "fixtures" / "persist.avi")
    session = service.upload_video(build_upload_file(source_video), {}, "operator-1").session

    service._process_session_job(session.session_id, uploaded_video_service_module.threading.Event())

    reloaded = JsonlIncidentRepository(str(tmp_path / "incidents"))
    items = reloaded.list_session_events(session.session_id)

    assert items
    assert items[0].source_type == "uploaded_video"
