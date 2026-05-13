from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase55_realtime_ws_contract_markers():
    route_text = (ROOT / "backend/app/api/drone_routes.py").read_text(encoding="utf-8")
    hook_text = (ROOT / "frontend/src/hooks/useDroneSimulation.js").read_text(encoding="utf-8")

    assert "/ws/drone-simulation" in route_text
    assert "type" in route_text
    assert "source_type" in route_text
    assert "operator_review_required" in route_text
    assert "telemetry" in route_text
    assert "frame_status" in route_text
    assert "mission_status" in route_text
    assert "detection_event" in route_text
    assert "fusion_update" in route_text
    assert "/ws/drone-simulation" in hook_text
