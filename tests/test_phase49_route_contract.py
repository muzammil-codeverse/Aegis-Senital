"""
Phase 49 — Route contract tests.

Verifies that all expected route hashes are defined in the frontend
navigation/App configuration, and that the corresponding Playwright
E2E spec files exist.
"""
import os
import re
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_SRC = os.path.join(ROOT, 'frontend', 'src')
E2E_DIR = os.path.join(ROOT, 'frontend', 'e2e')

REQUIRED_ROUTES = [
    'dashboard',
    'drone-operations',
    'drone-simulation',
    'drone-mission-planner',
    'drone-fusion',
    'map-operations',
    'investigation',
    'cases',
    'model-governance',
    'uploaded-video-analysis',
]

REQUIRED_E2E_SPECS = [
    'command-center.spec.js',
    'drone-operations.spec.js',
    'map-operations.spec.js',
    'investigation.spec.js',
    'drone-fusion.spec.js',
    'cases.spec.js',
    'model-governance.spec.js',
    'uploaded-video.spec.js',
    'tactical-3d.spec.js',
]


def _search_frontend_for_route(route: str) -> bool:
    """Search frontend source files for the given route hash."""
    for dirpath, _dirnames, filenames in os.walk(FRONTEND_SRC):
        for filename in filenames:
            if filename.endswith(('.jsx', '.tsx', '.js', '.ts')):
                filepath = os.path.join(dirpath, filename)
                try:
                    content = open(filepath, encoding='utf-8', errors='replace').read()
                    if route in content:
                        return True
                except OSError:
                    continue
    return False


@pytest.mark.parametrize("route", REQUIRED_ROUTES)
def test_route_defined_in_frontend(route):
    """Each required route hash must appear somewhere in frontend source."""
    found = _search_frontend_for_route(route)
    assert found, (
        f"Route '{route}' not found in any frontend source file. "
        "Ensure it is defined in App.jsx, commandNavigation.js, or lazyRoutes.jsx."
    )


@pytest.mark.parametrize("spec_file", REQUIRED_E2E_SPECS)
def test_playwright_spec_exists(spec_file):
    """Each required E2E spec file must exist."""
    spec_path = os.path.join(E2E_DIR, spec_file)
    assert os.path.isfile(spec_path), (
        f"Playwright spec not found: {spec_file}. "
        "Phase 49 requires browser-level tests for all core routes."
    )


def test_playwright_config_exists():
    config = os.path.join(ROOT, 'frontend', 'playwright.config.js')
    assert os.path.isfile(config), "playwright.config.js must exist in frontend/"


def test_playwright_e2e_scripts_in_package_json():
    package_json = open(
        os.path.join(ROOT, 'frontend', 'package.json'), encoding='utf-8'
    ).read()
    assert '"e2e"' in package_json, "package.json must have an 'e2e' script"
    assert '"e2e:headed"' in package_json, "package.json must have an 'e2e:headed' script"


def test_e2e_utils_exist():
    utils_dir = os.path.join(E2E_DIR, 'utils')
    required = ['auth.js', 'navigation.js', 'assertions.js']
    for util in required:
        path = os.path.join(utils_dir, util)
        assert os.path.isfile(path), f"E2E util not found: e2e/utils/{util}"


def test_e2e_fixtures_exist():
    fixtures_dir = os.path.join(E2E_DIR, 'fixtures')
    assert os.path.isfile(os.path.join(fixtures_dir, 'testData.js')), (
        "e2e/fixtures/testData.js must exist"
    )


def test_e2e_no_forbidden_wording_in_specs():
    """E2E specs must not assert forbidden wording as expected content."""
    forbidden = [
        'Suspect confirmed', 'Identity confirmed', 'Target confirmed',
        'Criminal confirmed', 'Confirmed terrorist',
    ]
    for spec_file in REQUIRED_E2E_SPECS:
        spec_path = os.path.join(E2E_DIR, spec_file)
        if not os.path.isfile(spec_path):
            continue
        content = open(spec_path, encoding='utf-8').read()
        for phrase in forbidden:
            assert phrase not in content, (
                f"Spec '{spec_file}' contains forbidden phrase: '{phrase}'"
            )


def test_e2e_specs_use_safe_wording_assertions():
    """At least the investigation spec should assert safe wording."""
    investigation_spec = os.path.join(E2E_DIR, 'investigation.spec.js')
    assert os.path.isfile(investigation_spec)
    content = open(investigation_spec, encoding='utf-8').read()
    assert 'assertNoForbiddenWording' in content or 'forbidden' in content.lower(), (
        "investigation.spec.js should use the forbidden-wording assertion"
    )
