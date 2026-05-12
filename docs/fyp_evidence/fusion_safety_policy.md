# Fusion Safety Policy

## Overview

All Phase 46 fusion outputs are subject to the following safety constraints.

## Absolute Rules

1. Do not fabricate drone telemetry, frames, missions, detections, or fusion results
2. Do not claim identity confirmation
3. Do not claim criminality or guilt
4. Do not claim a simulated drone is a real aircraft
5. Do not bypass Phase 35 object authorization
6. Do not bypass Phase 36 evidence integrity
7. Do not bypass Phase 37 persistence
8. Do not bypass Phase 41 model governance
9. Do not bypass Phase 42 GIS authorization filtering
10. Do not bypass Phase 43 safe investigation language
11. Do not bypass Phase 45 simulated mission safety labels
12. Do not create frontend-only fake fusion

## Enforced Safe Wording

| Safe | Forbidden |
|------|-----------|
| candidate cross-source match | confirmed suspect |
| possible same subject | identity confirmed |
| possible route continuation | criminal confirmed |
| simulated aerial observation | target confirmed |
| operator review required | real drone pursuit |
| evidence-backed hypothesis | guilty |
| low-confidence transition | attacker confirmed |

## Implementation

- `_enforce_safe_wording()` in `drone_fusion_models.py` validates all `safe_summary` fields
- Pydantic `field_validator` is applied on every model that carries `safe_summary`
- LLM service `PROHIBITED_REWRITES` includes fusion-specific patterns
- `LLM_FUSION_SAFETY_CONTEXT` is defined and available for injection into LLM prompts

## Operator Review

All correlations and handoffs carry:

```python
operator_review_required = True
review_status = "pending"
```

Until an operator accepts, rejects, or marks inconclusive, fusion results must not be treated as confirmed.

## Map Overlay Safety

- Unauthorized source locations are hidden (no line rendered)
- If one endpoint is unauthorized, the correlation line is not shown
- Simulated drone observations are labelled with "Simulated" badge
