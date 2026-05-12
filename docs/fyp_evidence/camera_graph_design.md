# Camera Graph Design

## Overview

The camera graph is a directed, weighted graph representing the physical relationships between cameras in the Aegis Sentinel deployment area. It is the foundation for path reconstruction.

## Graph Structure

### Nodes

Each node represents a camera with a known geo profile:

- `camera_id`
- `name`
- `latitude`, `longitude`
- `heading_degrees`, `fov_degrees`
- `coverage_radius_meters`
- `region`

### Edges

Edges connect pairs of cameras within `max_edge_distance_meters` (default 500m). Each edge is bidirectional.

| Field | Description |
|---|---|
| `from_camera_id` / `to_camera_id` | Directed camera pair |
| `distance_meters` | Haversine distance |
| `estimated_walk_seconds` | `distance / walk_speed (1.4 m/s)` |
| `estimated_run_seconds` | `distance / run_speed (3.5 m/s)` |
| `estimated_vehicle_seconds` | `distance / vehicle_speed (8.0 m/s)` |
| `transition_score` | Proximity + FOV overlap bonus (0–1.0) |
| `fov_overlap` | True if coverage radii overlap |
| `geofence_penalty` | Penalty if geofence crossed (0–1.0) |

## Distance Calculation

Haversine formula (deterministic):

```
d = 2R * atan2(sqrt(a), sqrt(1-a))
a = sin(Δlat/2)² + cos(lat1)*cos(lat2)*sin(Δlon/2)²
R = 6,371,000 m
```

## Transition Score

```
proximity = max(0, 1 - distance/max_distance)
fov_bonus = 0.15 if fov_overlap else 0.0
score = min(1.0, proximity + fov_bonus)
```

## Authorization Filtering

Only cameras accessible to the requesting user (via `list_camera_geo_profiles(user)`) are included in the graph. Unauthorized cameras are completely excluded — no edges to/from them appear.

## Configuration

`configs/runtime/investigation.yaml` → `camera_graph` section:

```yaml
camera_graph:
  max_edge_distance_meters: 500
  walking_speed_mps: 1.4
  running_speed_mps: 3.5
  vehicle_speed_mps: 8.0
  use_fov_overlap: true
  use_geofence_penalty: true
```

## Phase 44 Extension

Drone simulation nodes will be added to the camera graph as aerial observation points with their own FOV cones and transition scores based on flight paths.
