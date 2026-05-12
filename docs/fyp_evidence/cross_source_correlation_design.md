# Cross-Source Correlation Design

## Algorithm

```
1. Collect FusionObservations in time window
2. Filter to observations with source_ref (evidence gate)
3. For each valid source pair:
   a. Compute time_score    = max(0, 1 - |Δt| / max_time_delta)
   b. Compute geo_score     = max(0, 1 - dist / max_dist)  [0 if geo_missing]
   c. Compute appearance_score  [0 if no appearance_ref or track_id]
   d. Compute event_type_score  [1.0 if same type, 0.8 if both high-risk]
   e. Compute mission_context_score  [0.7 if drone source involved]
4. confidence = weighted_sum(scores)
5. If confidence >= min_fusion_confidence: persist CrossSourceCorrelation
6. Emit WebSocket notification
7. Return safe, operator-reviewed results
```

## Evidence Gate

A correlation is only generated when:
- Both observations have `source_ref` set
- At least one has `evidence_refs` or `event_id`

If neither observation carries evidence references, no correlation is generated.

## Thresholds

| Parameter | Default |
|-----------|---------|
| max_time_delta_seconds | 20 |
| max_spatial_distance_meters | 120 |
| min_fusion_confidence | 0.35 |

## Output

```json
{
  "correlation_id": "corr_...",
  "source_pair": ["fixed_camera", "drone_simulation"],
  "confidence": 0.64,
  "confidence_breakdown": {
    "time_score": 0.80,
    "geo_score": 0.60,
    "appearance_score": 0.00,
    "event_type_score": 0.80,
    "mission_context_score": 0.70
  },
  "safe_summary": "Candidate cross-source observation requiring operator review.",
  "operator_review_required": true,
  "review_status": "pending"
}
```
