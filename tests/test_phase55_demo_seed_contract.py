from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase55_demo_seed_contract_markers():
    text = (ROOT / "scripts/seed_city_drone_demo.py").read_text(encoding="utf-8")
    assert "demo" in text
    assert "simulated" in text
    assert "operator_review_required" in text
    assert "fusion" in text.lower()
    assert "geofence" in text.lower()
    assert "case" in text.lower()
    assert "investigation" in text.lower()


def test_phase55_final_dashboard_data_check_script_exists():
    path = ROOT / "scripts/check_final_demo_dashboard_data.py"
    assert path.exists(), str(path)
