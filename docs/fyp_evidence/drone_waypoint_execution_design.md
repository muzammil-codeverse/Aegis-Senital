# Drone Waypoint Execution Design — Phase 45

## Overview

This document describes the waypoint-based execution architecture for the Aegis Sentinel simulated drone patrol planner. All execution is against the Cosys-AirSim simulator; no real UAV deployment is involved.

## Waypoint Model

Each `DroneWaypoint` carries:

| Field | Type | Description |
|-------|------|-------------|
| `waypoint_id` | str | Unique identifier |
| `sequence_index` | int | Zero-based order in route |
| `latitude` | float | WGS-84 latitude (-90..90) |
| `longitude` | float | WGS-84 longitude (-180..180) |
| `altitude_meters` | float | AGL altitude (must be > 0) |
| `velocity_mps` | float | Approach velocity (must be > 0) |
| `hold_seconds` | float | Dwell time at waypoint |
| `camera_action` | enum | none / capture_frame / record_clip / hover_and_observe |
| `label` | str? | Human-readable description |

Validation rejects: latitude outside ±90°, longitude outside ±180°, altitude ≤ 0, velocity ≤ 0.

## Coordinate Conversion

The `drone_coordinate_mapper` module converts between WGS-84 and Cosys-AirSim NED coordinates:

- **Home origin**: lat=30.1575, lon=71.5249, alt=0 (Multan simulation environment)
- **geo_to_ned(lat, lon, alt)** → NEDPoint(x=North, y=East, z=Down)
- **ned_to_geo(x, y, z)** → GeoPoint(latitude, longitude, altitude_meters)

The equirectangular approximation is used (accurate < 0.1% within 5 km radius).

## Route Estimation

`DroneMissionService.estimate_route()` computes:
- **distance**: sum of haversine distances between consecutive waypoints
- **duration**: segment distance ÷ average velocity + hold time per waypoint

## Mission Session Lifecycle

```
DRAFT → (operator starts) → EXECUTING → COMPLETED
                         → PAUSED → EXECUTING
                         → CANCELLED
                         → FAILED (simulator disconnected)
```

## Execution Flow

1. Operator selects a mission plan with ≥2 waypoints
2. `POST /api/drone-missions/{id}/start` creates a `DroneMissionSession`
3. `DroneMissionExecutionService.start_mission()` checks simulator connectivity
4. If simulator disconnected → immediate `FAILED` + `SIMULATOR_DISCONNECTED` event (no fake telemetry)
5. If connected → issue `moveOnPath` to AirSim with NED-converted waypoints
6. As drone reaches each waypoint → telemetry point appended, `WAYPOINT_REACHED` event recorded
7. On completion → `COMPLETED` status + mission report generated

## No Fake Telemetry Guarantee

The execution service never generates synthetic position data. If the simulator disconnects mid-mission, the mission transitions to `FAILED` immediately. Telemetry is only recorded when the simulator provides real position data.

## Storage

| File | Contents |
|------|----------|
| `storage/drone_missions/missions.jsonl` | Mission plans |
| `storage/drone_missions/sessions.jsonl` | Execution sessions |
| `storage/drone_missions/telemetry/telemetry.jsonl` | Telemetry points |
| `storage/drone_missions/events.jsonl` | Lifecycle events |
| `storage/drone_missions/reports/reports.jsonl` | Post-mission reports |
