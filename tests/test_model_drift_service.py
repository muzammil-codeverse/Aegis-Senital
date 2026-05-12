from app.services.model_drift_service import summarize_drift_for_model


def test_drift_insufficient_without_events():
    out = summarize_drift_for_model("nonexistent_model_xyz")
    assert out["drift_status"] == "insufficient_data"
    assert out["sample_count"] == 0
