from app.models.uploaded_video_models import (
    UploadedVideoProcessingStatus,
    UploadedVideoProgress,
    UploadedVideoReport,
    UploadedVideoSession,
)


def test_uploaded_video_session_defaults():
    session = UploadedVideoSession(
        original_filename="demo.avi",
        safe_filename="uvs_demo.avi",
        storage_uri="storage/uploaded_videos/uvs_demo.avi",
        hash_sha256="abc123",
        created_by="user-1",
    )

    assert session.source_type == "uploaded_video"
    assert session.status == "uploaded"
    assert session.progress.frames_processed == 0


def test_uploaded_video_report_and_status_models():
    status = UploadedVideoProcessingStatus(
        session_id="uvs_123",
        status="processing",
        progress=UploadedVideoProgress(frames_processed=5, total_frames=10, percent=50.0),
        active=True,
        event_count=2,
    )
    report = UploadedVideoReport(
        session_id="uvs_123",
        model_caveats=["Operator review required."],
    )

    assert status.progress.percent == 50.0
    assert report.model_caveats == ["Operator review required."]
