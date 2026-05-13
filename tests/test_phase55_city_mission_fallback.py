from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_phase55_city_mission_presets_have_runtime_routes():
    payload = yaml.safe_load((ROOT / "configs/runtime/drone_city_missions.yaml").read_text(encoding="utf-8"))
    root = (payload or {}).get("drone_city_missions") or {}
    runtime_compat = root.get("runtime_compatibility") or {}
    assert "CityEnviron" in runtime_compat
    assert "AirSimNH" in runtime_compat
    assert "Blocks" in runtime_compat

    for preset in root.get("presets") or []:
        routes = preset.get("routes") or {}
        assert "city_route" in routes
        assert "neighborhood_route" in routes
        assert "compact_route" in routes


def test_phase55_city_mission_runner_has_fallback_statuses():
    text = (ROOT / "scripts/run_city_drone_mission_demo.py").read_text(encoding="utf-8")
    assert "completed_fallback" in text
    assert "degraded_fallback_complete" in text
    assert "completed_with_warnings" in text
