from app.services.drone.drone_camera_registry import (
    SUPPORTED_DRONE_CAMERAS,
    build_drone_source_id,
    list_drone_camera_sources,
)


def test_phase54_drone_camera_registry_has_required_sources():
    sources = list_drone_camera_sources("drone_sim_01")
    source_ids = {item.source_id for item in sources}
    for camera_name in SUPPORTED_DRONE_CAMERAS:
        assert build_drone_source_id("drone_sim_01", camera_name) in source_ids


def test_phase54_drone_camera_registry_metadata_flags_are_simulated():
    sources = list_drone_camera_sources("drone_sim_01")
    first = sources[0].to_metadata()
    assert first["source_type"] == "drone_simulation"
    assert first["simulated"] is True
    assert first["operator_review_required"] is True
