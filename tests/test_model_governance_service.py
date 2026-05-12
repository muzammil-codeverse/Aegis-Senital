from app.services.model_governance_service import evaluate_promotion, evaluate_runtime_model_governance


def test_governance_development_not_failed():
    rep = evaluate_runtime_model_governance(profile="development")
    assert rep["status"] in {"healthy", "degraded", "disabled"}


def test_promotion_rejects_empty_metrics():
    res = evaluate_promotion(model_key="phone_detector", target_version="v1", exception_approved=False)
    assert res.allowed is False
    assert any("metrics" in r for r in res.reasons)


def test_promotion_exception_allows():
    res = evaluate_promotion(model_key="phone_detector", target_version="v1", exception_approved=True)
    assert res.allowed is True
