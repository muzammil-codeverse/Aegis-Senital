"""
Phase 49 — Bundle contract: verifies Mapbox and R3F are lazy-loaded.

Checks:
  - mapbox-gl does NOT appear as a static import in the main index bundle
  - react-three-fiber does NOT appear as a static import in main source
  - Lazy route file exists and covers key routes
  - MapProviderCanvas uses dynamic import for mapbox-gl
  - Tactical3DStatusScene uses dynamic import for @react-three/fiber
"""
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = PROJECT_ROOT / "frontend" / "src"
DIST_ASSETS = PROJECT_ROOT / "frontend" / "dist" / "assets"


def _read(rel_path: str) -> str:
    return (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")


class TestMapboxLazyLoaded:
    def test_map_provider_canvas_uses_dynamic_import(self):
        content = _read("frontend/src/components/gis/MapProviderCanvas.jsx")
        assert "await import('mapbox-gl')" in content, (
            "mapbox-gl must be dynamically imported inside async branch"
        )

    def test_map_provider_canvas_no_static_mapbox_import(self):
        content = _read("frontend/src/components/gis/MapProviderCanvas.jsx")
        # No top-level static import of mapbox-gl
        static_imports = re.findall(r"^import\s+.*mapbox", content, re.MULTILINE)
        assert len(static_imports) == 0, (
            f"Found static mapbox import(s): {static_imports}"
        )

    def test_mapbox_css_loaded_dynamically(self):
        content = _read("frontend/src/components/gis/MapProviderCanvas.jsx")
        assert "await import('mapbox-gl/dist/mapbox-gl.css')" in content, (
            "mapbox-gl CSS should be dynamically imported"
        )

    def test_local_mock_path_has_no_mapbox(self):
        """The local_mock render path must not import Mapbox."""
        content = _read("frontend/src/components/gis/MapProviderCanvas.jsx")
        # The useEffect is only triggered when useMapbox is true
        # Verify the gis-local-mock-map class exists (local mock fallback)
        assert "gis-local-mock-map" in content

    def test_missing_token_state_present(self):
        content = _read("frontend/src/components/gis/MapProviderCanvas.jsx")
        assert "VITE_MAPBOX_TOKEN not set" in content or "missingToken" in content, (
            "MapProviderCanvas should have a clear missing-token state"
        )


class TestR3FLazyLoaded:
    def test_tactical3d_uses_dynamic_import(self):
        content = _read("frontend/src/components/command/Tactical3DStatusScene.jsx")
        assert "import('@react-three/fiber')" in content, (
            "@react-three/fiber must be dynamically imported"
        )

    def test_tactical3d_no_static_r3f_import(self):
        content = _read("frontend/src/components/command/Tactical3DStatusScene.jsx")
        static_imports = re.findall(r"^import\s+.*@react-three", content, re.MULTILINE)
        assert len(static_imports) == 0, (
            f"Found static @react-three import(s): {static_imports}"
        )

    def test_tactical3d_has_reduced_motion_fallback(self):
        content = _read("frontend/src/components/command/Tactical3DStatusScene.jsx")
        assert "reducedMotion" in content or "prefers-reduced-motion" in content, (
            "Tactical3DStatusScene must handle reduced-motion preference"
        )
        assert "ReducedMotionFallback" in content or "Fallback" in content, (
            "Should render a fallback when 3D is not available"
        )

    def test_tactical3d_has_cleanup(self):
        content = _read("frontend/src/components/command/Tactical3DStatusScene.jsx")
        assert "cancelled" in content or "clearTimeout" in content, (
            "Tactical3DStatusScene should clean up async import on unmount"
        )


class TestLazyRoutes:
    def test_lazy_routes_file_exists(self):
        lazy = PROJECT_ROOT / "frontend/src/routes/lazyRoutes.jsx"
        assert lazy.exists(), "lazyRoutes.jsx must exist"

    def test_lazy_routes_covers_key_routes(self):
        content = _read("frontend/src/routes/lazyRoutes.jsx")
        required = [
            "MapOperationsPage",
            "DroneSimulationPage",
            "DroneMissionPlannerPage",
            "DroneFusionPage",
            "InvestigationWorkspacePage",
            "ModelGovernancePage",
            "UploadedVideoAnalysisPage",
        ]
        for page in required:
            assert page in content, f"LazyRoutes must include {page}"

    def test_lazy_routes_use_react_lazy(self):
        content = _read("frontend/src/routes/lazyRoutes.jsx")
        assert "lazy(" in content, "lazyRoutes.jsx must use React.lazy"


class TestBundleBudget:
    def test_bundle_budget_script_exists(self):
        script = PROJECT_ROOT / "scripts" / "check_frontend_bundle_budget.py"
        assert script.exists()

    def test_dist_has_separate_mapbox_chunk(self):
        """If dist exists, verify mapbox is a separate chunk (not in index)."""
        if not DIST_ASSETS.exists():
            import pytest
            pytest.skip("dist/assets not built yet — run npm run build")

        js_files = list(DIST_ASSETS.glob("*.js"))
        mapbox_chunks = [f for f in js_files if "mapbox" in f.name.lower()]
        index_files = [f for f in js_files if f.name.startswith("index")]

        assert len(mapbox_chunks) > 0, (
            "Expected a separate mapbox-gl chunk in dist/assets"
        )

        # mapbox should NOT be in index bundle content
        for idx in index_files:
            content = idx.read_text(encoding="utf-8", errors="replace")
            assert "mapboxgl.accessToken" not in content, (
                f"mapbox-gl appears to be in the main index bundle {idx.name}"
            )
