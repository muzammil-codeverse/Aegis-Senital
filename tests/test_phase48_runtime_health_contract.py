"""
Phase 48 runtime health contract tests.
Validates that the runtime status hook covers required subsystems.
"""
import os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RUNTIME_STATUS_FILE = os.path.join(ROOT, 'frontend', 'src', 'hooks', 'useRuntimeStatus.js')

# All subsystems that must be represented as section keys inside useRuntimeStatus.js.
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
    assert os.path.isfile(RUNTIME_STATUS_FILE)


@pytest.mark.parametrize("subsystem", REQUIRED_SUBSYSTEMS)
def test_runtime_status_covers_subsystem(subsystem):
    src = open(RUNTIME_STATUS_FILE).read()
    assert subsystem in src, f"Subsystem '{subsystem}' not found in useRuntimeStatus.js"


def test_runtime_status_has_refresh():
    src = open(RUNTIME_STATUS_FILE).read()
    assert 'refresh' in src


def test_runtime_status_has_polling():
    src = open(RUNTIME_STATUS_FILE).read()
    assert 'pollMs' in src or 'setInterval' in src or 'timer' in src


def test_runtime_status_no_forbidden_wording():
    src = open(RUNTIME_STATUS_FILE).read().lower()
    forbidden = ['identity confirmed', 'suspect confirmed', 'target confirmed', 'confirmed threat']
    for phrase in forbidden:
        assert phrase not in src, f"Forbidden phrase '{phrase}' in useRuntimeStatus.js"
