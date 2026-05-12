"""
Phase 48 frontend reliability contract tests.
Validates that required scripts, docs, and source artifacts exist.
Does not parse JSX in a brittle way.
"""
import os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def path(*parts):
    return os.path.join(ROOT, *parts)


# ---------------------------------------------------------------------------
# Script existence
# ---------------------------------------------------------------------------

def test_safe_wording_script_exists():
    assert os.path.isfile(path('scripts', 'check_frontend_safe_wording.py'))


def test_bundle_budget_script_exists():
    assert os.path.isfile(path('scripts', 'check_frontend_bundle_budget.py'))


def test_accessibility_script_exists():
    assert os.path.isfile(path('scripts', 'check_frontend_accessibility_static.py'))


def test_validate_runtime_script_exists():
    assert os.path.isfile(path('scripts', 'validate_runtime.py'))


# ---------------------------------------------------------------------------
# Navigation source
# ---------------------------------------------------------------------------

def test_command_navigation_source_exists():
    assert os.path.isfile(path('frontend', 'src', 'navigation', 'commandNavigation.js'))


def test_command_navigation_has_drone_operations():
    src = open(path('frontend', 'src', 'navigation', 'commandNavigation.js')).read()
    assert 'Drone Operations' in src


def test_command_navigation_has_drone_fusion_route():
    src = open(path('frontend', 'src', 'navigation', 'commandNavigation.js')).read()
    assert 'drone-fusion' in src


def test_command_navigation_has_drone_simulation_route():
    src = open(path('frontend', 'src', 'navigation', 'commandNavigation.js')).read()
    assert 'drone-simulation' in src


def test_command_navigation_has_intelligence_group():
    src = open(path('frontend', 'src', 'navigation', 'commandNavigation.js')).read()
    assert 'Intelligence' in src


# ---------------------------------------------------------------------------
# Safe wording in navigation
# ---------------------------------------------------------------------------

FORBIDDEN_WORDING = [
    'identity confirmed',
    'suspect confirmed',
    'target confirmed',
    'criminal confirmed',
    'attacker confirmed',
    'real drone pursuit',
    'confirmed threat',
    'confirmed terrorist',
]


def test_no_forbidden_wording_in_navigation():
    src = open(path('frontend', 'src', 'navigation', 'commandNavigation.js')).read().lower()
    for phrase in FORBIDDEN_WORDING:
        assert phrase not in src, f"Forbidden phrase '{phrase}' found in commandNavigation.js"


# ---------------------------------------------------------------------------
# Lazy routes
# ---------------------------------------------------------------------------

def test_lazy_routes_file_exists():
    assert os.path.isfile(path('frontend', 'src', 'routes', 'lazyRoutes.jsx'))


def test_lazy_routes_has_drone_fusion():
    src = open(path('frontend', 'src', 'routes', 'lazyRoutes.jsx')).read()
    assert 'DroneFusionPage' in src


def test_lazy_routes_has_map_operations():
    src = open(path('frontend', 'src', 'routes', 'lazyRoutes.jsx')).read()
    assert 'MapOperationsPage' in src


def test_lazy_routes_uses_react_lazy():
    src = open(path('frontend', 'src', 'routes', 'lazyRoutes.jsx')).read()
    assert 'lazy(' in src


# ---------------------------------------------------------------------------
# Error boundary
# ---------------------------------------------------------------------------

def test_error_boundary_exists():
    assert os.path.isfile(path('frontend', 'src', 'components', 'layout', 'CommandErrorBoundary.jsx'))


def test_error_boundary_no_stack_trace_display():
    src = open(path('frontend', 'src', 'components', 'layout', 'CommandErrorBoundary.jsx')).read()
    # Should not render raw error.stack to the DOM
    assert 'error.stack' not in src or 'production' in src


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

def test_vitest_config_exists():
    assert os.path.isfile(path('frontend', 'vitest.config.js'))


def test_test_setup_file_exists():
    assert os.path.isfile(path('frontend', 'src', 'test', 'setupTests.js'))


def test_navigation_test_exists():
    assert os.path.isfile(path('frontend', 'src', 'navigation', 'commandNavigation.test.js'))


def test_runtime_strip_test_exists():
    assert os.path.isfile(path('frontend', 'src', 'components', 'command', 'RuntimeStatusStrip.test.jsx'))


def test_review_queue_test_exists():
    assert os.path.isfile(path('frontend', 'src', 'components', 'command', 'ReviewQueuePanel.test.jsx'))


def test_drone_hub_test_exists():
    assert os.path.isfile(path('frontend', 'src', 'pages', 'DroneOperationsHub.test.jsx'))


def test_drone_fusion_test_exists():
    assert os.path.isfile(path('frontend', 'src', 'pages', 'DroneFusionPage.test.jsx'))


# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

def test_frontend_reliability_doc_exists():
    assert os.path.isfile(path('docs', 'fyp_evidence', 'frontend_reliability_and_testing.md'))


def test_frontend_performance_doc_exists():
    assert os.path.isfile(path('docs', 'fyp_evidence', 'frontend_performance_hardening.md'))


def test_component_test_plan_doc_exists():
    assert os.path.isfile(path('docs', 'fyp_evidence', 'command_center_component_test_plan.md'))


# ---------------------------------------------------------------------------
# Common state components
# ---------------------------------------------------------------------------

def test_loading_state_exists():
    assert os.path.isfile(path('frontend', 'src', 'components', 'common', 'LoadingState.jsx'))


def test_empty_state_exists():
    assert os.path.isfile(path('frontend', 'src', 'components', 'common', 'EmptyState.jsx'))


def test_error_state_exists():
    assert os.path.isfile(path('frontend', 'src', 'components', 'common', 'ErrorState.jsx'))


def test_permission_denied_state_exists():
    assert os.path.isfile(path('frontend', 'src', 'components', 'common', 'PermissionDeniedState.jsx'))
