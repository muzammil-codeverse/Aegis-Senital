import pytest
from fastapi import HTTPException

from app.api.object_authorization import can_access_uploaded_video_session
from app.models.security_models import UserAccount
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


def _user(role: str, user_id: str) -> UserAccount:
    return UserAccount(
        user_id=user_id,
        username=user_id,
        display_name=user_id,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
    )


def test_uploaded_video_rejects_unsafe_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(uploaded_video_service_module, "get_incident_repository", lambda: build_incident_repository(tmp_path))
    monkeypatch.setattr(uploaded_video_service_module, "get_case_service", lambda: build_case_service(tmp_path))
    monkeypatch.setattr(uploaded_video_service_module, "ModelPool", FakeModelPool)
    monkeypatch.setattr(uploaded_video_service_module, "StreamProcessor", FakeStreamProcessor)
    service = UploadedVideoService(config=uploaded_video_config(tmp_path))
    source_video = create_test_video(tmp_path / "fixtures" / "demo.avi")
    bad_upload = build_upload_file(source_video)
    bad_upload.filename = "../demo.avi"

    with pytest.raises(HTTPException):
        service.upload_video(bad_upload, {}, "operator-1")


def test_uploaded_video_object_access_follows_creator_and_supervisor(tmp_path, monkeypatch):
    monkeypatch.setattr(uploaded_video_service_module, "get_incident_repository", lambda: build_incident_repository(tmp_path))
    monkeypatch.setattr(uploaded_video_service_module, "get_case_service", lambda: build_case_service(tmp_path))
    monkeypatch.setattr(uploaded_video_service_module, "ModelPool", FakeModelPool)
    monkeypatch.setattr(uploaded_video_service_module, "StreamProcessor", FakeStreamProcessor)
    service = UploadedVideoService(config=uploaded_video_config(tmp_path))
    source_video = create_test_video(tmp_path / "fixtures" / "demo.avi")
    session = service.upload_video(build_upload_file(source_video), {}, "operator-1").session

    monkeypatch.setattr("app.services.uploaded_video_service.get_uploaded_video_service", lambda: service)

    owner = _user("operator", "operator-1")
    viewer = _user("viewer", "viewer-1")
    supervisor = _user("supervisor", "supervisor-1")

    assert can_access_uploaded_video_session(owner, session.session_id) is True
    assert can_access_uploaded_video_session(viewer, session.session_id) is False
    assert can_access_uploaded_video_session(supervisor, session.session_id) is True
