from __future__ import annotations

from pathlib import Path

from app.models.incident_models import IncidentEventRecord
from app.repositories.incident_repository import JsonlIncidentRepository


def test_merge_event_metadata_links_clip_summary(tmp_path):
    repo = JsonlIncidentRepository(str(tmp_path / "inc"))
    repo.append_event(
        IncidentEventRecord(
            event_id="evt_link",
            source_type="uploaded_video",
            camera_id="uploaded:uvs_1",
            session_id="uvs_1",
            event_type="motion",
            summary="s",
            metadata={"seed": True},
        )
    )
    ok = repo.merge_event_metadata(
        "evt_link",
        {
            "uploaded_video_replay_clip": {
                "clip_id": "uvclip_9",
                "hash_sha256": "aa" * 32,
                "event_id": "evt_link",
            },
        },
    )
    assert ok
    loaded = repo.get_event("evt_link")
    assert loaded is not None
    assert loaded.metadata.get("uploaded_video_replay_clip", {}).get("clip_id") == "uvclip_9"
