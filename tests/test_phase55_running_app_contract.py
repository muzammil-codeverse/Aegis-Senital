from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase55_running_app_contract_scripts_exist():
    required = [
        ROOT / "scripts/launch_city_drone_fyp_demo.py",
        ROOT / "scripts/verify_running_demo_app.py",
        ROOT / "scripts/validate_city_drone_fyp_demo.py",
    ]
    for path in required:
        assert path.exists(), str(path)


def test_phase55_running_app_contract_markers():
    launch_text = (ROOT / "scripts/launch_city_drone_fyp_demo.py").read_text(encoding="utf-8")
    verify_text = (ROOT / "scripts/verify_running_demo_app.py").read_text(encoding="utf-8")

    assert "configure_drone_multicamera_settings.py" in launch_text
    assert "seed_city_drone_demo.py" in launch_text
    assert "uvicorn" in launch_text
    assert "npm" in launch_text
    assert "demo_runtime" in launch_text

    assert "backend_reachable" in verify_text
    assert "frontend_reachable" in verify_text
    assert "drone_status_api" in verify_text
    assert "analytics_api" in verify_text
