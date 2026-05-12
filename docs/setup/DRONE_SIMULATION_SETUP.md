# Drone Simulation Setup

This document records the dependency preparation for future Phase 44 (Drone Simulation Foundation) and subsequent phases.

## What was installed

### Python Dependencies
The following core packages were installed in `.venv`:
- `cosysairsim` (active Python client)
- `msgpack-rpc-python`
- `pymavlink`
- `mavsdk`
- Geospatial libraries: `geopy`, `pyproj`, `shapely`, `networkx`
- Utilities: `opencv-python`, `numpy`, `pandas`, `pyyaml`

*Note: The old `airsim` PyPI package failed to build on Python 3.12 due to NumPy compatibility issues. The newer, maintained `cosysairsim` PyPI package was installed instead, preserving environment integrity.*

### External Tools Directory
External tools are stored outside the main repository to prevent ballooning the repo size.
Directory: `C:\AegisExternalTools\drone_sim`

### Cosys-AirSim
A clone of Cosys-AirSim has been configured to reside at:
`C:\AegisExternalTools\drone_sim\cosys_airsim\Cosys-AirSim`
This provides the active Unreal Engine simulation APIs.

### Frontend Dependencies
Map and 3D packages were added (if not already present):
- `mapbox-gl`
- `three`
- `@react-three/fiber`
- `@react-three/drei`
- `gsap`

## What is optional and manual

- **Microsoft AirSim**: We defaulted to Cosys-AirSim as it's an actively maintained fork.
- **Unreal Engine**: Building the Unreal project has been postponed to a later phase to save time and bandwidth.
- **PX4/Gazebo & QGroundControl**: Install via manual download as necessary. PX4/Gazebo environment is heavy and skipped for this preparation step.

## Expected Ports
- AirSim Host: `127.0.0.1`
- AirSim Port: `41451`

## Future Phase 44 Usage
Phase 44 will utilize these tools to:
- Connect the Aegis Sentinel backend to a running simulation via `cosysairsim` client.
- Control virtual drones using the MAVSDK/pymavlink libraries.
- Combine drone telemetry with the geospatial frontend features using Mapbox and React Three Fiber.
