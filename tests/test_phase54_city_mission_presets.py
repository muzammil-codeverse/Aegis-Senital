from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_phase54_city_mission_presets_exist_and_required_names():
    path = ROOT / "configs" / "runtime" / "drone_city_missions.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    presets = (payload.get("drone_city_missions") or {}).get("presets") or []
    names = {item.get("name") for item in presets}
    required = {
        "perimeter_patrol",
        "incident_response",
        "crowd_monitoring",
        "traffic_corridor_scan",
        "fixed_camera_handoff_demo",
    }
    assert required.issubset(names)


def test_phase54_city_mission_presets_use_safe_simulation_flags():
    path = ROOT / "configs" / "runtime" / "drone_city_missions.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    presets = (payload.get("drone_city_missions") or {}).get("presets") or []
    assert presets, "Expected city mission presets"
    for preset in presets:
        assert preset.get("simulated_geo") is True
        assert str(preset.get("safe_wording") or "").strip() != ""
