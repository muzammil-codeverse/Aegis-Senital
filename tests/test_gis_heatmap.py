"""Heatmap aggregation tests (see also tests/test_gis_service.py)."""

from __future__ import annotations

from app.services.gis_service import _severity_weight


def test_severity_weight_ordering():
    w = {"low": 1, "medium": 3, "high": 7, "critical": 12}
    assert _severity_weight("critical", w) > _severity_weight("low", w)
