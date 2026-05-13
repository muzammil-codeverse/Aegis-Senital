from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


REQUIRED_DOCS = [
    ROOT / "docs/fyp_evidence/city_drone_simulation_design.md",
    ROOT / "docs/fyp_evidence/city_drone_demo_runbook.md",
    ROOT / "docs/fyp_evidence/final_fyp_demo_runbook.md",
    ROOT / "docs/fyp_evidence/phase55_drone_demo_readiness_report.md",
]


def test_phase55_documentation_files_exist():
    for path in REQUIRED_DOCS:
        assert path.exists(), str(path)


def test_phase55_documentation_mentions_runtime_and_fallback():
    report = (ROOT / "docs/fyp_evidence/phase55_drone_demo_readiness_report.md").read_text(encoding="utf-8").lower()
    assert "selected runtime" in report
    assert "fallback" in report
    assert "simulated drone feed" in report
    assert "operator review required" in report
