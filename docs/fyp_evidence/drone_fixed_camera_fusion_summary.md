# Phase 46 — Drone + Fixed Camera Fusion Summary

## Purpose

Phase 46 connects the simulated drone to the rest of Aegis Sentinel as a cross-source analytical asset.  
The drone becomes a moving camera source, GIS-aware aerial sensor, mission-aware telemetry source, and a contributor to investigation path reconstruction, case/evidence workflows, analytics, and operator triage.

Fusion correlations are **candidate relationships** between observations from different sources.  
They are **not confirmations of identity or guilt**.

## Source Types

| Source | Description |
|--------|-------------|
| `fixed_camera` | Live CCTV camera with GIS geo profile |
| `drone_simulation` | Cosys-AirSim simulated aerial camera |
| `drone_mission` | Patrol mission waypoint/telemetry events |
| `uploaded_video` | Analyst-provided video evidence |

## Valid Source Pairs for Correlation

- `fixed_camera` ↔ `drone_simulation`
- `fixed_camera` ↔ `drone_mission`
- `drone_mission` ↔ `uploaded_video`
- `drone_simulation` ↔ `uploaded_video`
- `fixed_camera` ↔ `uploaded_video`

## Scoring Model

```
confidence =
  time_score        × 0.30
+ geo_score         × 0.25
+ appearance_score  × 0.20
+ event_type_score  × 0.15
+ mission_ctx_score × 0.10
```

- `min_fusion_confidence = 0.35` — correlations below this are suppressed
- Scores are deterministic and reproducible given the same inputs

## Confidence Breakdown

Each `CrossSourceCorrelation` includes a `FusionConfidenceBreakdown` with individual component scores.  
This breakdown is surfaced in the UI and included in case exports.

## Operator Review Workflow

1. Fusion service generates `CrossSourceCorrelation` with `review_status=pending`
2. Operator views correlation in `DroneFusionPage` with confidence breakdown
3. Operator selects: **Accept**, **Reject**, or **Inconclusive**
4. Review is persisted with timestamp, reviewer, and notes
5. Accepted correlations may be weighted more heavily in path hypotheses
6. Rejected correlations must not increase path confidence
7. All review actions are audited

## Safe Wording Requirements

All fusion outputs must use safe wording:

| Safe | Forbidden |
|------|-----------|
| `candidate cross-source match` | `confirmed suspect` |
| `possible same subject` | `identity confirmed` |
| `possible route continuation` | `criminal confirmed` |
| `simulated aerial observation` | `real drone pursuit` |
| `operator review required` | `guilty` |

The `_enforce_safe_wording()` validator is applied on all `safe_summary` fields.

## Limitations

- Fusion correlations are hypotheses, not facts
- Simulated drone observations are not real aircraft data
- No auto-confirmation of identity is permitted
- Geo scoring is disabled when `geo_missing=True`
- Appearance scoring requires explicit `appearance_ref` or `track_id`
- All results carry `operator_review_required=True`

## How It Supports the FYP Demo

Phase 46 enables a full demonstration of:
1. Fixed camera detects weapon → generates `FusionObservation`
2. Drone simulation nearby → generates `FusionObservation` (simulated)
3. Fusion correlation computed → `CrossSourceCorrelation` with confidence breakdown
4. Operator reviews in `DroneFusionPage` → accepts/rejects
5. Accepted correlation appears in case timeline
6. Investigation path includes fusion steps
7. LLM context explicitly labels fusion as candidate relationship
8. Map overlay shows correlation line (geo-available endpoints only)
