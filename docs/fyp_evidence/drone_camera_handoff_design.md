# Drone-Camera Handoff Design

## Purpose

Handoff suggestions identify when a fixed camera and a drone observation are spatially co-located,  
suggesting that both may have observed activity in the same area during overlapping time windows.

Handoffs are **suggestions for operator review**, not automatic transfers of tracking.

## Trigger Scenarios

| Trigger | Description |
|---------|-------------|
| `suggest_handoffs_for_event` | A fixed-camera event has nearby cameras or drone waypoints |
| `suggest_handoffs_for_mission` | A drone mission waypoint is near one or more fixed cameras |
| `suggest_handoffs_near_location` | Aerial observation near a lat/lon with nearby cameras |

## Algorithm

```
For each source event / mission waypoint:
  1. Query GIS for nearby camera profiles within radius_meters
  2. Check object authorization for each camera (hidden if unauthorized)
  3. Compute confidence = max(0, 1 - dist / radius) × 0.8
  4. If confidence > 0: create DroneCameraHandoff, persist, return
```

## Output

```json
{
  "handoff_id": "handoff_...",
  "from_source_type": "fixed_camera",
  "from_source_id": "cam_01",
  "to_source_type": "drone_simulation",
  "to_source_id": "drone_sim_01",
  "reason": "nearby aerial observation",
  "confidence": 0.58,
  "safe_summary": "Possible route continuation. Operator review required.",
  "operator_review_required": true
}
```

## Authorization

- Cameras the user cannot access are **not included** in handoff suggestions
- GIS nearby camera query is filtered through `can_access_camera`
- If one side of a handoff is unauthorized, the handoff is not generated

## Safety

All handoff summaries must pass `_enforce_safe_wording()`.  
No handoff may claim certainty of subject movement.
