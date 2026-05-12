"""
Phase 49 — Accessibility regression contract.

Verifies that the static accessibility checker passes with zero blocking
warnings for user-facing inputs/buttons/images, and that the checker
script itself is present and functional.
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "scripts" / "check_frontend_accessibility_static.py"
PYTHON = sys.executable


def _run_checker(*extra_args):
    result = subprocess.run(
        [PYTHON, str(CHECKER)] + list(extra_args),
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    return result


class TestAccessibilityCheckerExists:
    def test_checker_script_present(self):
        assert CHECKER.exists(), f"Accessibility checker not found at {CHECKER}"

    def test_checker_is_runnable(self):
        result = _run_checker("--warn-only")
        # Script should exit cleanly (0) in warn-only mode regardless of findings
        assert result.returncode == 0, (
            f"Checker exited with {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestAccessibilityZeroWarnings:
    def test_no_blocking_warnings(self):
        """The checker must exit 0 AND report no issues after Phase 49 fixes."""
        result = _run_checker()
        assert result.returncode == 0, (
            f"Accessibility checker found blocking issues (exit {result.returncode}).\n"
            f"stdout: {result.stdout}"
        )
        assert "No accessibility issues found." in result.stdout, (
            f"Expected zero issues but got:\n{result.stdout}"
        )

    def test_warn_only_also_passes(self):
        result = _run_checker("--warn-only")
        assert result.returncode == 0
        # In warn-only mode, either "No accessibility issues found." or
        # the warn-only footer should appear.
        assert (
            "No accessibility issues found." in result.stdout
            or "warn-only mode" in result.stdout
        )


class TestKeyComponentsHaveAriaLabels:
    """Spot-checks that high-risk components gained aria-label attributes."""

    def _grep(self, rel_path: str, pattern: str) -> bool:
        target = PROJECT_ROOT / rel_path
        if not target.exists():
            return False
        return pattern in target.read_text(encoding="utf-8")

    def test_command_palette_has_aria_label(self):
        assert self._grep(
            "frontend/src/components/command/CommandPalette.jsx",
            'aria-label="Search command palette"',
        )

    def test_cases_page_search_has_aria_label(self):
        assert self._grep(
            "frontend/src/pages/CasesPage.jsx",
            'aria-label="Search cases"',
        )

    def test_camera_geo_profile_drawer_has_aria_labels(self):
        text = (PROJECT_ROOT / "frontend/src/components/gis/CameraGeoProfileDrawer.jsx").read_text(encoding="utf-8")
        assert 'aria-label="Latitude"' in text
        assert 'aria-label="Longitude"' in text

    def test_fusion_review_controls_has_aria_label(self):
        assert self._grep(
            "frontend/src/components/drone-fusion/FusionReviewControls.jsx",
            'aria-label="Review notes"',
        )

    def test_investigation_path_reconstruction_has_aria_labels(self):
        text = (PROJECT_ROOT / "frontend/src/components/investigation/PathReconstructionPanel.jsx").read_text(encoding="utf-8")
        assert 'aria-label="Case ID"' in text
        assert 'aria-label="Event ID"' in text

    def test_model_governance_drift_has_aria_label(self):
        assert self._grep(
            "frontend/src/components/model-governance/ModelDriftPanel.jsx",
            'aria-label="Model ID"',
        )

    def test_watchlist_panel_has_aria_labels(self):
        text = (PROJECT_ROOT / "frontend/src/components/identity/WatchlistPanel.jsx").read_text(encoding="utf-8")
        assert 'aria-label="Watchlist reason"' in text
        assert 'aria-label="Expiry days"' in text
