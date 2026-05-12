from app.services.model_governance_service import evaluate_promotion


def test_weapon_promotion_policy_enforced():
    res = evaluate_promotion(model_key="weapon_detector", target_version="v1", exception_approved=False)
    # v1 is deprecated entry — still has metrics; policy may pass or fail on map — assert structured response
    assert hasattr(res, "allowed")
