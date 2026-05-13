# City Drone Simulation Design

## Scope
Phase 55 finalizes the simulated city-drone subsystem inside Aegis Sentinel for local demo use. The design keeps strict simulator honesty: no fabricated telemetry, no fake mission success, and no real-world pursuit language.

## Runtime Strategy
- Runtime installation root: `C:\AegisExternalTools\drone_sim\runtime\environments`.
- Runtime inventory file: `storage/drone_sim/runtime_inventory.json`.
- Selection priority: `CityEnviron` -> `AirSimNH` -> `Blocks` fallback.
- Strict city validation fails if only Blocks is selected.
- Blocks fallback remains preserved and explicitly labeled (`fallback_used=true`).

## Current Runtime Status (This Machine)
- `Blocks`: installed.
- `AirSimNH`: archive downloaded but no Windows executable detected.
- `CityEnviron`: multipart package not fully usable in this run window.
- Result: strict city runtime unavailable; fallback mode only.

## Multi-Camera Setup
- Vehicle: `Drone1`.
- Cameras: `front_center`, `front_left`, `front_right`, `downward`, `rear`.
- Scene RGB capture: `1280x720`.
- FOV: front `90`, downward `110`.
- Existing `settings.json` is backed up before rewrite.

## Stream and Inference Flow
- Drone frames are captured through the Cosys-AirSim client.
- Frames are adapted with drone metadata and sent through `StreamProcessor.process_decoded_packet()`.
- No toy path is used for drone inference.
- Metadata always carries:
  - `source_type=drone_simulation`
  - `simulated=true`
  - `operator_review_required=true`

## API and Real-Time Contract
- REST contract includes runtime, cameras, telemetry, events, and stream start/stop endpoints.
- WebSocket route: `/ws/drone-simulation`.
- Typed real-time payloads:
  - `telemetry`
  - `frame_status`
  - `mission_status`
  - `detection_event`
  - `fusion_update`
  - `runtime_status`

## Mission Presets
- Config: `configs/runtime/drone_city_missions.yaml`.
- Each mission has runtime-specific paths:
  - `city_route`
  - `neighborhood_route`
  - `compact_route`
- Runtime compatibility section maps CityEnviron/AirSimNH/Blocks behavior.

## GIS, Fusion, Investigation, Cases, Analytics
- GIS layers include drone trail, route overlays, FOV, and handoff arrows.
- Fusion, investigation, and case pipelines remain operator-reviewed and safety-labeled.
- Analytics include drone runtime health, mission status, event counts, and fusion pending counts.

## Safety Language Policy
Required wording:
- Simulated drone feed
- Simulated aerial observation
- Candidate cross-source observation
- Possible movement path
- Operator review required
- Evidence-backed hypothesis
- Demo scenario
- Insufficient data

Forbidden wording is blocked in UI/content checks (no identity/guilt/target confirmation claims).
