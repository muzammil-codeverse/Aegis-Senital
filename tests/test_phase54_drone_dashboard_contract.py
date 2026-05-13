from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase54_drone_dashboard_contract_files_exist():
    required = [
        ROOT / "frontend/src/pages/DroneSimulationPage.jsx",
        ROOT / "frontend/src/components/drone/DroneCameraGrid.jsx",
        ROOT / "frontend/src/components/drone/DroneRuntimeSelector.jsx",
        ROOT / "frontend/src/components/drone/DroneMissionQuickActions.jsx",
        ROOT / "frontend/src/components/streaming/LiveStreamPanel.jsx",
        ROOT / "backend/app/api/drone_routes.py",
    ]
    for path in required:
        assert path.exists(), str(path)


def test_phase54_drone_dashboard_contract_references_camera_latest_frame_endpoint():
    api_text = (ROOT / "backend/app/api/drone_routes.py").read_text(encoding="utf-8")
    fe_api_text = (ROOT / "frontend/src/api/droneSimulationApi.js").read_text(encoding="utf-8")
    page_text = (ROOT / "frontend/src/pages/DroneSimulationPage.jsx").read_text(encoding="utf-8").lower()

    assert "/api/drone-simulation/cameras/{camera_name}/latest-frame" in api_text
    assert "/api/drone-simulation/cameras/" in fe_api_text
    assert "simulated aerial observation" in page_text
    assert "operator review required" in page_text
