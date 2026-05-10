from __future__ import annotations

from inference.anomaly.schemas import AnomalyPrediction


_SEVERITY_THRESHOLDS = {
    "critical": 0.85,
    "high": 0.70,
    "medium": 0.50,
    "low": 0.30,
}


def severity_from_score(score: float, thresholds: dict | None = None) -> str:
    t = thresholds or _SEVERITY_THRESHOLDS
    if score >= t.get("critical", 0.85):
        return "critical"
    if score >= t.get("high", 0.70):
        return "high"
    if score >= t.get("medium", 0.50):
        return "medium"
    return "low"


def fuse_predictions(
    rule_predictions: list[AnomalyPrediction],
    model_prediction: AnomalyPrediction | None,
    violence_prediction: AnomalyPrediction | None,
    weights: dict | None = None,
    thresholds: dict | None = None,
) -> list[AnomalyPrediction]:
    """
    Weighted fusion of rule-engine and model predictions per anomaly type.

    Returns one AnomalyPrediction per anomaly_type with fused scores and
    source attribution. Only predictions above the 'low' threshold are emitted.
    """
    w = weights or {"rule_engine": 0.40, "video_model": 0.40, "object_context": 0.20}
    t = thresholds or _SEVERITY_THRESHOLDS
    low_thresh = t.get("low", 0.30)

    # Group rule predictions by type
    by_type: dict[str, list[AnomalyPrediction]] = {}
    for pred in rule_predictions:
        by_type.setdefault(pred.anomaly_type, []).append(pred)

    # Inject model and violence predictions
    if model_prediction:
        by_type.setdefault(model_prediction.anomaly_type, []).append(model_prediction)
    if violence_prediction:
        by_type.setdefault(violence_prediction.anomaly_type, []).append(violence_prediction)

    fused: list[AnomalyPrediction] = []
    for anomaly_type, preds in by_type.items():
        rule_scores = [p.score for p in preds if p.source == "rule_engine"]
        model_scores = [p.score for p in preds if "adapter" in p.source or p.source == "video_model"]
        violence_scores = [p.score for p in preds if "violence" in p.source]

        rule_score = max(rule_scores) if rule_scores else 0.0
        model_score = max(model_scores) if model_scores else 0.0
        violence_score = max(violence_scores) if violence_scores else 0.0

        fused_score = (
            rule_score * w.get("rule_engine", 0.40)
            + model_score * w.get("video_model", 0.40)
            + violence_score * w.get("object_context", 0.20)
        )

        # If only rule scores present, use pure rule score
        if not model_scores and not violence_scores and rule_scores:
            fused_score = rule_score

        if fused_score < low_thresh:
            continue

        # Merge evidence from all contributing predictions
        evidence: dict = {}
        for p in preds:
            evidence.update(p.evidence)
        evidence["contributing_sources"] = list({p.source for p in preds})
        evidence["rule_score"] = round(rule_score, 4)
        evidence["model_score"] = round(model_score, 4)

        max_duration = max(p.duration_seconds for p in preds)
        track_ids = list({tid for p in preds for tid in p.track_ids})
        confidence = _confidence_from_preds(preds, fused_score)

        fused.append(AnomalyPrediction(
            camera_id=preds[0].camera_id,
            anomaly_type=anomaly_type,
            score=round(fused_score, 4),
            severity=severity_from_score(fused_score, t),
            confidence=round(confidence, 4),
            source="fusion",
            duration_seconds=max_duration,
            track_ids=track_ids,
            evidence=evidence,
            requires_review=True,
        ))

    return sorted(fused, key=lambda p: p.score, reverse=True)


def _confidence_from_preds(preds: list[AnomalyPrediction], fused_score: float) -> float:
    """Confidence grows with number of agreeing sources and score magnitude."""
    n_sources = len({p.source for p in preds})
    base = fused_score * 0.80
    source_bonus = min(0.15, (n_sources - 1) * 0.05)
    return min(0.95, base + source_bonus)
