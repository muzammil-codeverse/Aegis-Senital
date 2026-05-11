from __future__ import annotations

import re
from pathlib import Path


def _forbidden_patterns():
    return [
        re.compile(r"identity\s+confirmed", re.I),
        re.compile(r"suspect\s+confirmed", re.I),
        re.compile(r"criminal\s+identified", re.I),
        re.compile(r"attacker\s+confirmed", re.I),
    ]


def test_identity_ui_sources_avoid_forbidden_wording():
    root = Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "identity"
    forbidden = _forbidden_patterns()
    for path in root.glob("*.jsx"):
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert not pattern.search(text), f"{path.name} contains forbidden wording: {pattern.pattern}"


def test_identity_candidate_api_strings_use_safe_language():
    from app.services import identity_candidate_service as ics

    text = Path(ics.__file__).read_text(encoding="utf-8")
    assert "Possible identity match" in text or "possible identity match" in text.lower()
