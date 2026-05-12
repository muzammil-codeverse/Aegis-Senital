from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
FRONTEND_SRC = FRONTEND / "src"


def test_phase47_command_center_files_exist():
    required = [
        FRONTEND_SRC / "navigation" / "commandNavigation.js",
        FRONTEND_SRC / "styles" / "commandCenterTheme.js",
        FRONTEND_SRC / "styles" / "commandCenter.css",
        FRONTEND_SRC / "components" / "layout" / "CommandCenterShell.jsx",
        FRONTEND_SRC / "components" / "layout" / "CommandSidebar.jsx",
        FRONTEND_SRC / "components" / "layout" / "CommandTopBar.jsx",
        FRONTEND_SRC / "components" / "layout" / "CommandStatusBar.jsx",
        FRONTEND_SRC / "components" / "layout" / "CommandPageHeader.jsx",
        FRONTEND_SRC / "components" / "layout" / "CommandSection.jsx",
        FRONTEND_SRC / "components" / "command" / "CommandPalette.jsx",
        FRONTEND_SRC / "components" / "command" / "RuntimeStatusStrip.jsx",
        FRONTEND_SRC / "components" / "command" / "ReviewQueuePanel.jsx",
        FRONTEND_SRC / "components" / "command" / "OperationsTimeline.jsx",
        FRONTEND_SRC / "components" / "command" / "Tactical3DStatusScene.jsx",
        FRONTEND_SRC / "hooks" / "useCommandPalette.js",
        FRONTEND_SRC / "hooks" / "useGlobalSearch.js",
        FRONTEND_SRC / "hooks" / "useRuntimeStatus.js",
        FRONTEND_SRC / "pages" / "DroneOperationsHub.jsx",
        ROOT / "scripts" / "check_frontend_safe_wording.py",
    ]
    for path in required:
        assert path.exists(), str(path)


def test_phase47_routes_and_navigation_groups_exist():
    app_text = (FRONTEND_SRC / "App.jsx").read_text(encoding="utf-8")
    nav_text = (FRONTEND_SRC / "navigation" / "commandNavigation.js").read_text(encoding="utf-8")

    assert "drone-fusion" in app_text
    assert "drone-operations" in app_text
    assert "CommandCenterShell" in app_text

    for group in ["Overview", "Live Operations", "Geospatial", "Drone Operations", "Intelligence"]:
        assert group in nav_text


def test_phase47_safe_wording_script_passes():
    result = subprocess.run(
        [sys.executable, "scripts/check_frontend_safe_wording.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_phase47_frontend_build_passes():
    npm = shutil.which("npm")
    if not npm:
        raise AssertionError("npm is required for the Phase 47 frontend build contract test")
    result = subprocess.run(
        [npm, "run", "build"],
        cwd=FRONTEND,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
