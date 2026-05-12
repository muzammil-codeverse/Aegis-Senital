"""Tests for Phase 46 frontend contract stability."""
from pathlib import Path

FRONTEND_SRC = Path(__file__).parent.parent / "frontend" / "src"


def test_drone_fusion_api_js_exists():
    assert (FRONTEND_SRC / "api" / "droneFusionApi.js").exists()


def test_drone_fusion_hook_exists():
    assert (FRONTEND_SRC / "hooks" / "useDroneFusion.js").exists()


def test_drone_fusion_page_exists():
    assert (FRONTEND_SRC / "pages" / "DroneFusionPage.jsx").exists()


def test_drone_fusion_components_exist():
    comp_dir = FRONTEND_SRC / "components" / "drone-fusion"
    assert comp_dir.exists()
    required = [
        "FusionOverviewPanel.jsx",
        "FusionObservationTable.jsx",
        "CrossSourceCorrelationPanel.jsx",
        "FusionConfidenceBreakdown.jsx",
        "HandoffSuggestionPanel.jsx",
        "FusionTimeline.jsx",
        "FusionReviewControls.jsx",
        "FusionSafetyBadge.jsx",
        "FusionMapOverlay.jsx",
    ]
    for comp in required:
        assert (comp_dir / comp).exists(), f"Missing component: {comp}"


def test_fusion_api_has_required_exports():
    api_code = (FRONTEND_SRC / "api" / "droneFusionApi.js").read_text(encoding="utf-8")
    required_exports = [
        "listFusionObservations",
        "runCorrelation",
        "listCorrelations",
        "acceptCorrelation",
        "rejectCorrelation",
        "markCorrelationInconclusive",
        "listHandoffs",
        "suggestHandoffsForEvent",
        "getFusionTimeline",
        "getFusionHealth",
    ]
    for fn in required_exports:
        assert fn in api_code, f"Missing export: {fn}"


def test_fusion_page_no_fake_data():
    page_code = (FRONTEND_SRC / "pages" / "DroneFusionPage.jsx").read_text(encoding="utf-8")
    # Must not contain hardcoded mock correlations or fake telemetry
    assert "mockCorrelations" not in page_code
    assert "fakeObservations" not in page_code
