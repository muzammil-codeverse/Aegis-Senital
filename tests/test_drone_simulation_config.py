from inference.config_runtime import load_runtime_config

import scripts.validate_runtime as validate_runtime


def test_drone_simulation_config_loads():
    cfg = load_runtime_config("drone_simulation")
    root = cfg.get("drone_simulation") or {}

    assert root.get("provider") == "cosys_airsim"
    assert root.get("stream", {}).get("source_type") == "drone_simulation"
    assert root.get("stream", {}).get("pseudo_camera_id") == "drone_sim_01"
    assert root.get("safety", {}).get("label_as_simulated") is True
    assert root.get("safety", {}).get("prohibit_real_world_claims") is True


def test_validate_drone_simulation_configuration_reports_required_artifacts():
    results = validate_runtime.validate_drone_simulation_configuration("development")
    by_name = {item["name"]: item for item in results}

    assert by_name["drone simulation provider"]["status"] == "PASS"
    assert by_name["verify_drone_sim_runtime.py"]["status"] == "PASS"
