# Phase 56 — Final Live Drone Runtime Recovery & Defense Demo Report

**Date:** 2026-05-13  
**Project:** Aegis Sentinel AI — Final Year Project Defense  
**Phase:** 56 (Live Drone Runtime Recovery & Full System Validation)

---

## 1. Executive Summary

Phase 56 resolved all Phase 55 drone simulation blockers and delivered a fully operational city/neighborhood AirSim runtime (AirSimNH) integrated into the Aegis Sentinel AI platform. All required success conditions are met:

| Condition | Status |
|---|---|
| AirSimNH installed and detected | PASS |
| City runtime launches successfully | PASS |
| RPC port 41451 connects | PASS |
| Drone telemetry retrieved | PASS |
| front_center camera frame captured (256×144) | PASS |
| Drone mission execution in city runtime | PASS |
| Dashboard receives live drone status, telemetry, camera/feed state | PASS |
| Strict city validation passes (no Blocks fallback) | PASS |
| 1026 unit tests passing | PASS |
| validate_runtime 112/117 checks passed | PASS |

---

## 2. Runtime Environment

- **Selected Runtime:** AirSimNH (Microsoft AirSim v1.8.1 neighborhood environment)
- **Runtime Path:** `C:\AegisExternalTools\drone_sim\runtime\environments\AirSimNH\AirSimNH\WindowsNoEditor\AirSimNH.exe`
- **RPC Host:Port:** 127.0.0.1:41451
- **Server Protocol Version:** 1 (AirSim v1.8.1 compatible)
- **Python Client:** cosysairsim 3.3.0 with 3-arg simGetImages compatibility patch
- **GPU:** NVIDIA RTX 4060 Laptop (CUDA available, AirSim rendering via DirectX 12)
- **Blocks Fallback Used:** No (strict city runtime enforced)

---

## 3. Critical Technical Discovery: simGetImages Compatibility

**Root Cause:** The AirSimNH binary registers `simGetImages` with **3 arguments** — `(requests, vehicle_name, external)` — while the cosysairsim 3.3 Python client's `VehicleClient.simGetImages()` sends only 2. The rpclib error message format has "Expected" and "got" labels swapped from intuitive order: "Expected: 2, got: 3" means *we sent 2, function needs 3*.

**Fix Applied:**
- `scripts/smoke_city_drone_runtime.py`: Uses low-level `rpc.call("simGetImages", [req_dict], "", False)` — bypasses the Python stub, sends all 3 args.
- `backend/app/services/drone/cosys_airsim_client.py` `get_multi_camera_frames()`: Same 3-arg raw RPC approach with graceful fallback to 2-arg for older builds.
- **All existing tests remain green** (1026 pass, 4 skip).

---

## 4. Runtime Validation Results

### 4.1 City Runtime Smoke (`smoke_city_drone_runtime.py --require-city --strict`)
```json
{
  "status": "ok",
  "selected_runtime": "AirSimNH",
  "fallback_used": false,
  "rpc_ok": true,
  "telemetry_ok": true,
  "front_center_frame_ok": true,
  "frame_width": 256,
  "frame_height": 144,
  "gps": {
    "latitude": 47.641468,
    "longitude": -122.140165,
    "altitude": 122.15
  }
}
```

### 4.2 Live City Mission Demo (`smoke_drone_mission.py --strict`)
- Mission config verified (safety flags: simulated_only=true, prohibit_real_world_claims=true)
- Models validated: Pydantic OK, geo/NED round-trip OK
- Mission created and persisted: `mission_b0834f3ae803`, distance=7.3m
- Simulator commands issued and mission completed
- Telemetry collected: 4 points
- Mission events recorded: 5 events
- Mission status reflects waypoint progress and completion

### 4.3 Dashboard REST APIs (`smoke_drone_dashboard_apis.py --with-auth`)
- All required endpoints: **PASS**
- Endpoints: health, drone-simulation/status/runtime/cameras/latest-frame/telemetry/events, drone-missions, drone-fusion/health/correlations, analytics/overview, gis/layers, investigations, cases, uploaded-videos

### 4.4 WebSocket/Polling Smoke (`smoke_drone_ws_updates.py`)
- Mode: polling_fallback (websocket-client package not installed)
- Required types seen: runtime_status, telemetry, frame_status
- Optional types seen: mission_status
- Forbidden wording: none detected

### 4.5 Model Asset Validation (`smoke_all_model_assets.py`)
- YOLOv8 detection: PASS
- SAM2 segmentation: PASS
- Open-Vocab GroundingDINO: PASS
- InsightFace identity: PASS

### 4.6 Drone Pipeline Smoke (`smoke_drone_simulation_pipeline.py`)
- Safe labels confirmed: "Simulated aerial observation", "Candidate cross-source observation", "Operator review required"
- No crashes, no forbidden wording

### 4.7 Full Validation Suite
- **pytest:** 1026 passed, 4 skipped
- **compileall backend:** 0 errors
- **compileall scripts:** 0 errors
- **validate_runtime:** 112/117 checks passed (PASSED — all required OK)

### 4.8 Uploaded Video Workflow
- Demo video: `demo_crowd_street.mp4` (simulated aerial CCTV scene)
- Workflow: uploaded → processing → completed
- Report ready: True

---

## 5. Safe Wording Compliance

All system outputs use approved safe wording:
- "Simulated drone feed" / "Simulated aerial observation"
- "Candidate cross-source observation"
- "Possible movement path"
- "Operator review required"
- "Evidence-backed hypothesis"
- "Demo scenario"

No forbidden wording detected in any pipeline output:
- NOT: "Suspect confirmed", "Identity confirmed", "Target confirmed", "Criminal confirmed", "Attacker confirmed", "Confirmed terrorist", "Confirmed threat", "Real drone pursuit"

---

## 6. System Architecture (Live Demo)

```
AirSimNH.exe (port 41451)
    │
    ├── RPC: ping, confirmConnection, getMultirotorState
    ├── RPC: simGetImages (3-arg: requests, vehicle_name, external)
    └── RPC: moveToPositionAsync (waypoint flight)
         │
         ▼
CosysAirSimClient (backend/app/services/drone/)
    │
    ├── DroneSimulationService → /api/drone-simulation/*
    ├── DroneMissionExecutionService → /api/drone-missions
    ├── DroneFusionService → /api/drone-fusion/*
    └── StreamProcessor → process_decoded_packet()
         │
         ▼
FastAPI Backend (port 8000)
    │
    └── React Frontend (port 5173) → defense dashboard
```

---

## 7. Defense Demonstration Sequence

1. Open dashboard: http://localhost:5173
2. Navigate to Drone Simulation panel → observe live AirSimNH status
3. View real-time telemetry (GPS, altitude, orientation)
4. View front_center camera frame stream
5. Trigger demo mission → watch waypoint execution
6. Navigate to Fusion panel → see cross-source observation candidates
7. Navigate to Cases → see evidence-backed case with operator review flag
8. Navigate to Investigations → see hypothesis with "Insufficient data" guard
9. Navigate to Uploaded Videos → show processed demo_crowd_street.mp4 report
10. Navigate to Analytics → overview metrics
11. Navigate to GIS → layer visualisation

---

## 8. Known Limitations (Non-blocking for Defense)

- AirSimNH server protocol version = 1 (vs Cosys-AirSim minimum 4); cosmetic warning printed on connect, does not affect functionality
- WebSocket library (websocket-client) not installed; polling fallback used transparently
- CityEnviron not installed (would require additional 4+ GB download); AirSimNH provides equivalent neighborhood environment
- Frame resolution: 256×144 (AirSim minimal settings); adequate for demo

---

_Report generated by Phase 56 defense automation — Aegis Sentinel AI_
