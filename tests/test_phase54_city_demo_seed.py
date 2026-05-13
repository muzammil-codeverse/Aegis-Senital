from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase54_city_demo_seed_script_exists():
    path = ROOT / "scripts" / "seed_city_drone_demo.py"
    assert path.exists()


def test_phase54_city_demo_seed_contains_required_simulation_flags():
    text = (ROOT / "scripts" / "seed_city_drone_demo.py").read_text(encoding="utf-8")
    assert '"demo": True' in text
    assert '"simulated": True' in text
    assert '"operator_review_required": True' in text
    assert "multan" in text.lower()
