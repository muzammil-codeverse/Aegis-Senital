from fastapi.testclient import TestClient

from app.api import uploaded_video_routes as uploaded_video_routes_module
from app.models.security_models import UserAccount
from app.models.uploaded_video_models import (
    UploadedVideoProcessingStatus,
    UploadedVideoProgress,
    UploadedVideoSession,
    UploadedVideoUploadResponse,
)
from app.services import auth_service as auth_module
from main import app


def _user(role: str) -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
    )


class _FakeUploadedVideoService:
    def __init__(self) -> None:
        self.session = UploadedVideoSession(
            session_id="uvs_route",
            original_filename="demo.avi",
            safe_filename="uvs_route.avi",
            storage_uri="storage/uploaded_videos/uvs_route.avi",
            hash_sha256="abc123",
            created_by="user-supervisor",
        )

    def upload_video(self, file, options, user):
        del file, options, user
        return UploadedVideoUploadResponse(session=self.session)

    def get_session(self, session_id):
        return self.session if session_id == self.session.session_id else None

    def start_processing(self, session_id, user):
        del user
        return UploadedVideoProcessingStatus(session_id=session_id, status="queued", progress=UploadedVideoProgress(total_frames=10), active=True)

    def get_status(self, session_id, user=None):
        del user
        return UploadedVideoProcessingStatus(session_id=session_id, status="completed", progress=UploadedVideoProgress(frames_processed=10, total_frames=10, percent=100.0), active=False, report_ready=True, event_count=2)

    def get_timeline(self, session_id, user=None):
        del session_id, user
        return []

    def get_events(self, session_id, user=None):
        del session_id, user
        return []

    def cancel_processing(self, session_id, user):
        del user
        return UploadedVideoProcessingStatus(session_id=session_id, status="cancelled", progress=UploadedVideoProgress(total_frames=10), active=False)

    def create_case_from_session(self, session_id, body, user):
        del session_id, body, user
        return type("CaseRecord", (), {"model_dump": lambda self, mode="json": {"case_id": "case_uploaded"}})()

    def get_report(self, session_id, user=None):
        del session_id, user
        return type("Report", (), {"model_dump": lambda self, mode="json": {"session_id": "uvs_route", "model_caveats": ["review required"]}})()

    def list_sessions(self, created_by=None):
        del created_by
        return [self.session]


def test_uploaded_video_routes_expose_workflow(monkeypatch):
    users = {"supervisor": _user("supervisor")}
    auth_service = auth_module.get_auth_service()
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: users.get(token))
    service = _FakeUploadedVideoService()
    monkeypatch.setattr(uploaded_video_routes_module, "get_uploaded_video_service", lambda: service)

    client = TestClient(app, raise_server_exceptions=False)
    upload = client.post(
        "/api/uploaded-videos",
        headers={"Authorization": "Bearer supervisor"},
        files={"file": ("demo.avi", b"RIFFfake", "video/x-msvideo")},
        data={"options": "{}"},
    )
    assert upload.status_code == 200
    session_id = upload.json()["session"]["session_id"]

    process = client.post(f"/api/uploaded-videos/{session_id}/process", headers={"Authorization": "Bearer supervisor"})
    detail = client.get(f"/api/uploaded-videos/{session_id}", headers={"Authorization": "Bearer supervisor"})
    status = client.get(f"/api/uploaded-videos/{session_id}/status", headers={"Authorization": "Bearer supervisor"})
    report = client.get(f"/api/uploaded-videos/{session_id}/report", headers={"Authorization": "Bearer supervisor"})

    assert process.status_code == 200
    assert detail.status_code == 200
    assert status.json()["item"]["status"] == "completed"
    assert report.status_code == 200
