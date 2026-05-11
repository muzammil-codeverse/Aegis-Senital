from app.models.incident_models import IncidentEventRecord
from app.repositories.incident_repository import JsonlIncidentRepository


def test_incident_repository_persists_uploaded_video_events(tmp_path):
    repository = JsonlIncidentRepository(str(tmp_path / "incidents"))
    record = IncidentEventRecord(
        incident_id="inc_1",
        event_id="evt_1",
        source_type="uploaded_video",
        session_id="uvs_1",
        camera_id="uploaded:uvs_1",
        event_type="weapon_detected",
        severity="high",
        risk_score=0.9,
        summary="Possible event",
    )
    repository.append_event(record)

    assert repository.get_event("evt_1").session_id == "uvs_1"
    assert repository.list_session_events("uvs_1")[0].event_id == "evt_1"

    reloaded = JsonlIncidentRepository(str(tmp_path / "incidents"))
    assert reloaded.list_events({"source_type": "uploaded_video", "limit": 10})[0].event_id == "evt_1"
