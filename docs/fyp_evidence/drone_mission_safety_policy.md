# Drone Patrol Mission Safety Policy — Phase 45

## Purpose

This document defines the safety constraints enforced by the Aegis Sentinel Drone Patrol Mission Planner. These constraints ensure the system cannot be misused to create false impressions of real-world drone deployment, confirmed identities, or operational threats.

## Policy Constraints

### 1. Simulation-Only Enforcement

- All missions carry `simulated: true` — this field is immutable via API
- `prohibit_real_world_claims: true` is set in `drone_mission.yaml`
- The config key `simulated_only: true` must always be true
- Runtime validation (`validate_runtime.py`) checks this on every startup

### 2. Operator-in-the-Loop

- `require_operator_start: true` — missions cannot start without an explicit operator action via `POST /api/drone-missions/{id}/start`
- All artifacts carry `operator_review_required: true`
- Reports include the text: "Operator review required before any operational use"

### 3. Forbidden Wording

The following phrases are **never** to appear in any user-facing text, labels, logs, or reports:

| Forbidden | Reason |
|-----------|--------|
| "Real drone deployed" | Implies operational capability |
| "Target confirmed" | Implies identity/threat confirmation |
| "Suspect confirmed" | Implies criminal identification |
| "Criminal confirmed" | Implies judicial determination |
| "Pursuit confirmed" | Implies active law enforcement action |
| "Identity confirmed" | Implies biometric certainty |

### 4. Required Safe Wording

All labels, events, and reports must use one of these approved phrases:

| Safe Phrase | Context |
|-------------|---------|
| "Simulated drone mission" | Mission titles and headers |
| "Simulated aerial patrol" | Session status messages |
| "Candidate patrol route" | Mission plan descriptions |
| "Simulated aerial observation" | Observation/event labels |
| "Mission hypothesis" | Investigation integration |
| "Operator review required" | All reports and evidence |

### 5. Graceful Failure on Disconnection

- If Cosys-AirSim is not connected, missions fail to `FAILED` status immediately
- No synthetic/fake telemetry is ever generated
- A `SIMULATOR_DISCONNECTED` event is recorded with clear explanation
- The error message explicitly states the simulator is unavailable

### 6. Audit Trail

- Every mission lifecycle action is audited via `get_audit_log_service()`
- Audit actions: `DRONE_MISSION_CREATED`, `DRONE_MISSION_STARTED`, `DRONE_MISSION_PAUSED`, `DRONE_MISSION_RESUMED`, `DRONE_MISSION_CANCELLED`, `DRONE_MISSION_VIEWED`, `DRONE_MISSION_REPORT_VIEWED`
- `require_mission_audit: true` is set in config

### 7. RBAC Permissions

| Permission | Grants |
|-----------|--------|
| `drone:read` | List missions, view status, read telemetry/events/reports |
| `drone:mission` | Create, update, delete, start, pause, resume, cancel missions |
| `drone:control` | Required alongside `drone:mission` for execution actions |
| `gis:read` | Required for GIS layer integration |

### 8. Evidence Classification

All mission artifacts attached to cases must carry:
- `simulated: True`
- `operator_review_required: True`
- Evidence type: `drone_mission_report`, `drone_mission_telemetry_manifest`, or `drone_mission_event`

These evidence types are explicitly classified as simulation artifacts and cannot be promoted to operational evidence without separate review.

## Compliance Checklist

- [x] `simulated_only: true` in config
- [x] All models carry `simulated: bool = True`
- [x] All models carry `operator_review_required: bool = True`
- [x] No fake telemetry generated on simulator disconnect
- [x] All API responses include `simulated: true`
- [x] Forbidden phrases absent from all codebase strings
- [x] Audit logging on all lifecycle actions
- [x] Runtime validation checks safety flags
- [x] Frontend shows `MissionSafetyBadge` on all mission screens
