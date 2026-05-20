from app.models.uploaded_video_models import UploadedVideoCaseCreationRequest
from app.core.capabilities import CapabilityRegistry, CapabilityState, register_default_capabilities
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


class FailingStreamProcessor:
    def __init__(self, stream_id: str, source: str, model_pool: FakeModelPool) -> None:
        del stream_id, source, model_pool

    def process_decoded_packet(self, decoded_packet) -> dict:
        del decoded_packet
        raise RuntimeError("synthetic inference failure")


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
    report = service.get_report(upload.session.session_id)
    assert report is not None
    assert report.metadata["command_center"]["alert_ids"]
    assert service.get_command_center_links(upload.session.session_id)["alert_ids"]

    created = service.create_case_from_session(
        upload.session.session_id,
        UploadedVideoCaseCreationRequest(title="Uploaded session case"),
        "operator-1",
    )
    evidence = case_service.list_evidence(created.case_id)

    assert created.case_id
    assert evidence


def test_uploaded_video_processing_failure_persists_status_error(tmp_path, monkeypatch):
    incident_repository = build_incident_repository(tmp_path)
    case_service = build_case_service(tmp_path)
    monkeypatch.setattr(uploaded_video_service_module, "get_incident_repository", lambda: incident_repository)
    monkeypatch.setattr(uploaded_video_service_module, "get_case_service", lambda: case_service)
    monkeypatch.setattr(uploaded_video_service_module, "ModelPool", FakeModelPool)
    monkeypatch.setattr(uploaded_video_service_module, "StreamProcessor", FailingStreamProcessor)

    service = UploadedVideoService(config=uploaded_video_config(tmp_path))
    source_video = create_test_video(tmp_path / "fixtures" / "demo.avi")
    upload = service.upload_video(build_upload_file(source_video), {}, "operator-1")

    service._process_session_job(upload.session.session_id, uploaded_video_service_module.threading.Event())

    status = service.get_status(upload.session.session_id)
    session = service.get_session(upload.session.session_id)
    assert status.status == "failed"
    assert "synthetic inference failure" in status.last_error
    assert session.metadata["last_error"] == status.last_error


def test_uploaded_video_processing_updates_capability_registry(tmp_path, monkeypatch):
    registry = CapabilityRegistry()
    register_default_capabilities(registry)
    incident_repository = build_incident_repository(tmp_path)
    case_service = build_case_service(tmp_path)
    monkeypatch.setattr(uploaded_video_service_module, "get_capability_registry", lambda: registry)
    monkeypatch.setattr(uploaded_video_service_module, "get_incident_repository", lambda: incident_repository)
    monkeypatch.setattr(uploaded_video_service_module, "get_case_service", lambda: case_service)
    monkeypatch.setattr(uploaded_video_service_module, "ModelPool", FakeModelPool)
    monkeypatch.setattr(uploaded_video_service_module, "StreamProcessor", FakeStreamProcessor)

    service = UploadedVideoService(config=uploaded_video_config(tmp_path))
    source_video = create_test_video(tmp_path / "fixtures" / "demo.avi")
    upload = service.upload_video(build_upload_file(source_video), {}, "operator-1")

    service._process_session_job(upload.session.session_id, uploaded_video_service_module.threading.Event())

    assert registry.get("uploaded_video_pipeline").runtime_status.state == CapabilityState.READY
    assert registry.get("yolo_weapon_detector").runtime_status.state == CapabilityState.READY
    assert registry.get("yolo_phone_detector").runtime_status.state == CapabilityState.READY
    assert registry.get("tracking_engine").runtime_status.state == CapabilityState.READY
    assert registry.get("event_engine").runtime_status.state == CapabilityState.READY
