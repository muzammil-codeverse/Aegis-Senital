from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_drone_frontend_contract_files_exist():
    required = [
        ROOT / "frontend/src/api/droneSimulationApi.js",
        ROOT / "frontend/src/hooks/useDroneSimulation.js",
        ROOT / "frontend/src/components/drone/DroneStatusPanel.jsx",
        ROOT / "frontend/src/components/drone/DroneTelemetryPanel.jsx",
        ROOT / "frontend/src/components/drone/DroneControlPanel.jsx",
        ROOT / "frontend/src/components/drone/DroneVideoPreview.jsx",
        ROOT / "frontend/src/components/drone/DroneFlightPathPanel.jsx",
        ROOT / "frontend/src/components/drone/DroneMapOverlayPanel.jsx",
        ROOT / "frontend/src/components/drone/DroneSafetyBadge.jsx",
        ROOT / "frontend/src/pages/DroneSimulationPage.jsx",
    ]
    for path in required:
        assert path.exists(), str(path)


def test_drone_frontend_contract_references_route_api_and_safe_wording():
    app_text = (ROOT / "frontend/src/App.jsx").read_text(encoding="utf-8")
    api_text = (ROOT / "frontend/src/api/droneSimulationApi.js").read_text(encoding="utf-8")
    hook_text = (ROOT / "frontend/src/hooks/useDroneSimulation.js").read_text(encoding="utf-8")
    page_text = (ROOT / "frontend/src/pages/DroneSimulationPage.jsx").read_text(encoding="utf-8")
    page_lower = page_text.lower()

    assert "drone-simulation" in app_text
    assert "/api/drone-simulation/status" in api_text
    assert "/api/drone-simulation/frame/latest" in api_text
    assert "/ws/drone-simulation" in hook_text
    assert "simulated drone feed" in page_lower or "simulated aerial" in page_lower
