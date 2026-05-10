import pytest
from inference.anomaly.scoring import fuse_predictions, severity_from_score
from inference.anomaly.schemas import AnomalyPrediction


def _pred(anomaly_type, score, source="rule_engine", cam="cam1"):
    return AnomalyPrediction(
        camera_id=cam,
        anomaly_type=anomaly_type,
        score=score,
        severity=severity_from_score(score),
        confidence=score * 0.9,
        source=source,
        duration_seconds=5.0,
    )


def test_severity_mapping():
    assert severity_from_score(0.90) == "critical"
    assert severity_from_score(0.75) == "high"
    assert severity_from_score(0.55) == "medium"
    assert severity_from_score(0.20) == "low"


def test_fuse_predictions_single_rule():
    preds = [_pred("loitering", 0.65)]
    result = fuse_predictions(preds, None, None)
    assert len(result) == 1
    assert result[0].anomaly_type == "loitering"
    assert result[0].source == "fusion"


def test_fuse_predictions_below_threshold_filtered():
    preds = [_pred("loitering", 0.10)]  # below low threshold of 0.30
    result = fuse_predictions(preds, None, None)
    assert len(result) == 0


def test_fuse_predictions_model_and_rule():
    rule = _pred("violence", 0.55)
    model = _pred("violence", 0.70, source="pretrained_video")
    result = fuse_predictions([rule], model, None)
    assert len(result) == 1
    # Fused score should be between the two inputs
    assert result[0].score > 0.30


def test_fuse_predictions_multiple_types():
    preds = [_pred("loitering", 0.65), _pred("crowd_anomaly", 0.55)]
    result = fuse_predictions(preds, None, None)
    assert len(result) == 2
    types = {r.anomaly_type for r in result}
    assert "loitering" in types
    assert "crowd_anomaly" in types


def test_fuse_sorted_by_score_descending():
    preds = [_pred("loitering", 0.45), _pred("violence", 0.80)]
    result = fuse_predictions(preds, None, None)
    assert result[0].score >= result[-1].score


def test_fuse_evidence_merged():
    rule = _pred("violence", 0.60)
    rule.evidence = {"rule_key": "val1"}
    model = _pred("violence", 0.75, source="violence_visual_adapter")
    model.evidence = {"model_key": "val2"}
    result = fuse_predictions([rule], None, model)
    assert "contributing_sources" in result[0].evidence


def test_fuse_requires_review_always_true():
    preds = [_pred("loitering", 0.65)]
    result = fuse_predictions(preds, None, None)
    assert all(r.requires_review for r in result)
