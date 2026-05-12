# Drone Simulation Integration Summary

## Purpose

Phase 44 integrates the prepared Cosys-AirSim runtime into Aegis Sentinel as a simulated drone source. The integration treats the simulator as a first-class video, telemetry, GIS, and investigation source without presenting it as a real aircraft.

## Why Cosys-AirSim

- The project already had a prepared Windows runtime and Python client path.
- It exposes RPC access for telemetry, imagery, and basic multirotor commands.
- It supports repeatable academic testing without introducing live-flight risk.

## Simulator vs Real Drone Distinction

- All new models, APIs, GIS layers, and UI wording mark the source as simulated.
- Safe labels use language such as "Simulated drone feed" and "Simulated aerial observation".
- When the runtime is unavailable, the platform reports `disconnected` or `degraded` instead of inventing telemetry or frames.

## Integrated Surfaces

- Runtime config: `configs/runtime/drone_simulation.yaml`
- Backend services: Cosys-AirSim client, drone simulation service, session manager
- Inference path: simulated frame -> `DroneFrameAdapter` -> `StreamProcessor`
- GIS: dynamic drone marker, trail, and FOV through authorized map layers
- Investigation: drone observations can appear as `drone_observation` hypothesis steps
- API and WebSocket: status, telemetry, commands, frame access, and live telemetry updates
- Frontend: dedicated `#drone-simulation` page plus dashboard, map, analytics, and investigation integration

## Limitations

- This phase does not control a physical drone and must not be interpreted as one.
- The camera graph and GIS marker depend on configured home coordinates or available simulated telemetry.
- Live smoke execution still depends on the external simulator being started separately.

## Future Direction

- Replace or augment the simulator transport with PX4 and QGroundControl integration.
- Add richer camera FOV projection and mission planning overlays.
- Expand the session manager for multiple simulated drones when governance and authorization rules are ready.
