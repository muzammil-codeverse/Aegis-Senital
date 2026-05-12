from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models.gis_models import CameraGeoProfile, EventGeoMarker
from app.models.investigation_models import PathReconstructionRequest
from app.models.security_models import UserAccount, UserStatus
from app.services.path_reconstruction_service import reconstruct_path


def _user() -> UserAccount:
    return UserAccount(
        user_id="u-analyst",
        username="analyst",
        display_name="Analyst",
        role="analyst",
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
    )


def test_drone_observations_can_appear_in_path_hypothesis():
    now = datetime.now(timezone.utc).isoformat()
    gis_repo = MagicMock()
    gis_repo.list_camera_geo_profiles.return_value = [
        CameraGeoProfile(
            camera_id="drone_sim_01",
            name="Simulated Drone Feed",
            latitude=30.1575,
            longitude=71.5249,
            altitude_meters=40.0,
            metadata={"source_type": "drone_simulation", "simulated": True},
        )
    ]
    gis_repo.get_event_markers.return_value = [
        EventGeoMarker(
            event_id="event_drone_001",
            source_type="drone_simulation",
            camera_id="drone_sim_01",
            case_id="case_drone",
            event_type="drone_frame",
            severity="medium",
            latitude=30.1575,
            longitude=71.5249,
            altitude_meters=40.0,
            timestamp=now,
            title="Simulated aerial observation",
        )
    ]

    inv_repo = MagicMock()
    inv_repo.save_hypothesis.side_effect = lambda hypothesis: hypothesis

    response = reconstruct_path(
        PathReconstructionRequest(case_id="case_drone"),
        gis_repo,
        inv_repo,
        _user(),
    )

    assert response.status == "ok"
    assert response.hypotheses
    step = response.hypotheses[0].steps[0]
    assert step.step_type == "drone_observation"
    assert step.safe_label == "Simulated aerial observation"
    assert step.source_type == "drone_simulation"
