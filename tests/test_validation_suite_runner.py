from pathlib import Path


def test_run_full_validation_script_exists():
    text = Path("scripts/run_full_validation.py").read_text(encoding="utf-8")
    assert "PYTHONFAULTHANDLER" in text or "faulthandler" in text
    assert "pytest" in text


def test_run_validation_suite_script_exists():
    p = Path("scripts/run_validation_suite.py")
    assert p.exists()
    body = p.read_text(encoding="utf-8")
    assert "pytest" in body
