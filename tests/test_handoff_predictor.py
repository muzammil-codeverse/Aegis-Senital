from __future__ import annotations

from inference.correlation.handoff_predictor import _get


def test_handoff_predictor_get_supports_default_value() -> None:
    assert _get({}, "missing", 7) == 7

    class _Track:
        track_id = 5

    assert _get(_Track(), "track_id", 0) == 5
    assert _get(_Track(), "identity_id", "unknown") == "unknown"
