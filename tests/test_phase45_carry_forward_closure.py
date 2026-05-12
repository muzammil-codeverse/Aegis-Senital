"""Tests for Phase 45 carry-forward closure (Task 20 — last item)."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


def test_validate_drone_coordinate_mapping_script_exists():
    p = Path(__file__).parent.parent / "scripts" / "validate_drone_coordinate_mapping.py"
    assert p.exists(), "validate_drone_coordinate_mapping.py must exist"


def test_smoke_drone_mission_ws_load_script_exists():
    p = Path(__file__).parent.parent / "scripts" / "smoke_drone_mission_ws_load.py"
    assert p.exists(), "smoke_drone_mission_ws_load.py must exist"


def test_smoke_drone_fixed_camera_fusion_script_exists():
    p = Path(__file__).parent.parent / "scripts" / "smoke_drone_fixed_camera_fusion.py"
    assert p.exists(), "smoke_drone_fixed_camera_fusion.py must exist"


def test_drone_mission_repository_importable():
    from app.repositories.drone_mission_repository import DroneMissionRepository, get_drone_mission_repository
    assert DroneMissionRepository is not None


def test_drone_mission_repository_health_check(tmp_path):
    from app.repositories.drone_mission_repository import DroneMissionRepository
    repo = DroneMissionRepository(root_dir=tmp_path / "phase45_test")
    health = repo.health_check()
    assert health.get("status") in ("healthy", "ok")


def test_coordinate_mapper_round_trip():
    from app.services.drone.drone_coordinate_mapper import (
        HOME_LATITUDE, HOME_LONGITUDE, HOME_ALTITUDE, geo_to_ned, ned_to_geo
    )
    ned = geo_to_ned(HOME_LATITUDE + 0.001, HOME_LONGITUDE + 0.001, HOME_ALTITUDE + 30)
    geo = ned_to_geo(ned.x, ned.y, ned.z)
    assert abs(geo.latitude - (HOME_LATITUDE + 0.001)) < 1e-5
    assert abs(geo.longitude - (HOME_LONGITUDE + 0.001)) < 1e-5


def test_drone_fusion_repository_production_fail_fast():
    from app.repositories.drone_fusion_repository import DroneFusionRepository, DroneFusionRepositoryError
    with pytest.raises(DroneFusionRepositoryError):
        DroneFusionRepository(production_mode=True, production_required=True)


def test_drone_fusion_config_safety():
    from pathlib import Path
    import yaml
    cfg_path = Path(__file__).parent.parent / "configs" / "runtime" / "drone_fusion.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    assert cfg["drone_fusion"]["safety"]["safe_wording_required"] is True
    assert cfg["drone_fusion"]["safety"]["prohibit_guilt_language"] is True
