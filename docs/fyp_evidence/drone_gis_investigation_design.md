# Drone GIS and Investigation Design

## GIS Integration

The simulated drone is represented as a pseudo-camera with ID `drone_sim_01`.

- Telemetry updates refresh the drone geo profile.
- Authorized GIS layers show the simulated drone marker, trail, and camera FOV.
- The map keeps standard authorization filtering, so users without stream or camera access do not see the drone marker.
- Nearby fixed-camera queries can use the current drone position to support operator review.

## Camera Graph Integration

- The camera graph includes the simulated drone as a node when the user is authorized.
- If live telemetry is not yet present, the graph can fall back to the configured simulated home position.
- Standard distance-based edge generation allows the drone node to connect to nearby fixed cameras.

## Investigation Integration

Drone-origin observations are stored with safe wording and may become `drone_observation` steps in reconstructed paths.

Example semantics:

- step type: `drone_observation`
- safe label: `Simulated aerial observation`
- operator review required: `true`

This keeps the path hypothesis aligned with Phase 43 safe-language requirements. The platform describes the result as a candidate or possible movement path rather than a confirmed pursuit.

## Limitations

- The simulated flight path is not a forensic statement about a real aircraft.
- Temporal graph behavior is only as good as the received simulated telemetry cadence.
- Investigation confidence still depends on the quality of the underlying detections and geo profiles.

## Future PX4 / QGroundControl Path

- Introduce a provider abstraction parallel to `cosys_airsim`.
- Reuse the same packet, GIS, investigation, and RBAC surfaces.
- Keep explicit source labeling so simulated and live aerial systems cannot be confused.
