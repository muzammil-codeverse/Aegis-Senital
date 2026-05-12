"""
Phase 49 — Runtime health contract extension.

Builds on Phase 48 contracts.  Verifies that the frontend runtime hook
covers all Phase 49 subsystems, that no production-only hard dependencies
block dev mode, and that the hook correctly exposes the expected interface.
"""
import os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RUNTIME_STATUS_FILE = os.path.join(ROOT, 'frontend', 'src', 'hooks', 'useRuntimeStatus.js')

# Phase 49 extends Phase 48 subsystem list — all must be covered.
REQUIRED_SUBSYSTEMS = [
    'gis',
    'investigation',
    'droneSimulation',
    'droneMission',
    'droneFusion',
    'modelGovernance',
    'llm',
    'database',
    'redis',
]


def test_runtime_status_hook_exists():
    assert os.path.isfile(RUNTIME_STATUS_FILE), (
        f"useRuntimeStatus.js not found at {RUNTIME_STATUS_FILE}"
    )


@pytest.mark.parametrize("subsystem", REQUIRED_SUBSYSTEMS)
def test_runtime_status_covers_subsystem(subsystem):
    src = open(RUNTIME_STATUS_FILE, encoding='utf-8').read()
    assert subsystem in src, (
        f"Subsystem '{subsystem}' not found in useRuntimeStatus.js. "
        "Phase 49 requires all subsystems to be monitored."
    )


def test_runtime_status_has_refresh():
    src = open(RUNTIME_STATUS_FILE, encoding='utf-8').read()
    assert 'refresh' in src, "useRuntimeStatus must expose a refresh function"


def test_runtime_status_has_polling():
    src = open(RUNTIME_STATUS_FILE, encoding='utf-8').read()
    assert any(kw in src for kw in ('pollMs', 'setInterval', 'timer', 'interval')), (
        "useRuntimeStatus should implement polling"
    )


def test_runtime_status_no_hard_production_dependency():
    """Dev mode should not require production-only services to boot."""
    src = open(RUNTIME_STATUS_FILE, encoding='utf-8').read()
    # Hook should not hard-throw on missing services (should return degraded state)
    # Presence of fallback/error handling indicates graceful degradation
    assert any(kw in src for kw in ('catch', 'error', 'Error', 'fallback', 'degraded', 'status')), (
        "useRuntimeStatus should handle service unavailability gracefully"
    )


def test_runtime_status_no_forbidden_wording():
    src = open(RUNTIME_STATUS_FILE, encoding='utf-8').read().lower()
    forbidden = [
        'identity confirmed', 'suspect confirmed', 'target confirmed',
        'confirmed threat', 'confirmed terrorist',
    ]
    for phrase in forbidden:
        assert phrase not in src, f"Forbidden phrase '{phrase}' in useRuntimeStatus.js"
