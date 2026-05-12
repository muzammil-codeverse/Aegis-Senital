"""Tests for Phase 46 drone fusion REST endpoints."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


def test_drone_fusion_router_importable():
    from app.api.drone_fusion_routes import router
    assert router is not None


def test_drone_fusion_router_registered_in_main():
    from app.api.routes import router as main_router
    route_paths = [r.path for r in main_router.routes]
    assert any("drone-fusion" in p for p in route_paths), "drone-fusion routes must be registered"


def test_broadcast_fusion_event_importable():
    from app.api.drone_fusion_routes import broadcast_fusion_event
    assert callable(broadcast_fusion_event)


def test_ws_subscribers_dict_exists():
    from app.api.drone_fusion_routes import _ws_subscribers
    assert isinstance(_ws_subscribers, dict)
