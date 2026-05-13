from app.models.gis_models import CameraGeoProfile
from app.models.security_models import UserAccount, UserStatus
from app.services import gis_service


class _Repo:
    def list_camera_geo_profiles(self, user):
        del user
        return [
            CameraGeoProfile(camera_id="cam_fixed_01", name="Fixed 01", latitude=30.1575, longitude=71.5249),
        ]

    def get_event_markers(self, **kwargs):
        del kwargs
        return []

    def get_case_markers(self, **kwargs):
        del kwargs
        return []

    def list_geofences(self, user):
        del user
        return []


def _admin() -> UserAccount:
    return UserAccount(
        user_id="u-admin",
        username="admin",
        display_name="Admin",
        role="admin",
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
    )


def test_phase54_map_layers_include_city_drone_fields():
    layers = gis_service.build_map_layers(
        _Repo(),
        _admin(),
        None,
        start_time=None,
        end_time=None,
        severity=None,
        event_type=None,
        camera_id=None,
        case_id=None,
        source_type=None,
    )
    assert hasattr(layers, "drone_paths")
    assert hasattr(layers, "drone_mission_routes")
    assert hasattr(layers, "active_mission_paths")
    assert hasattr(layers, "fixed_camera_handoffs")
