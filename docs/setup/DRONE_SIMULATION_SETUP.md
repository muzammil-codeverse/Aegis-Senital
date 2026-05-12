# Drone Simulation Setup

This document outlines the state of the Drone Simulation environment for Phase 44.

## 1. Dependency layer status
- The `cosysairsim` Python client is fully installed in `.venv`.
- `msgpackrpc`, `pymavlink`, `mavsdk`, and geospatial packages are all installed and validated.
- **Note:** `cosysairsim` installed means the *Python client* is ready. It does *not* mean the simulator runtime is actually running.

## 2. Runtime simulator status
- The prebuilt **Blocks** simulator environment for Windows is downloaded and extracted at `C:\AegisExternalTools\drone_sim\runtime\environments\Blocks`.
- `settings.json` is configured in `~/Documents/AirSim/` with a default Multirotor and a `front_center` camera.
- The runtime has been tested and successfully communicates with the Python client over RPC.

## 3. How to launch simulator
Use the repo launcher so startup stays consistent and crash diagnostics are visible:

```powershell
python scripts\launch_blocks_runtime.py
```

If you need to launch it manually, use the same safe profile:

```powershell
cd C:\AegisExternalTools\drone_sim\runtime\environments\Blocks\Blocks_packaged_Windows_55_33\Windows
.\Blocks.exe -windowed -ResX=640 -ResY=480
```

If Windows shows an Unreal fatal error, check the latest crash summary with:

```powershell
python scripts\verify_drone_sim_runtime.py --strict
```

That command now prints the most recent crash context, including the GPU Unreal bound to during the failure.

## 4. How to verify RPC
Once the simulator is open, verify the RPC port is listening:
```powershell
netstat -ano | findstr 41451
```
You should see `LISTENING` on `0.0.0.0:41451`.

## 5. How to capture one frame
Run the included smoke script from the repository root:
```powershell
python scripts\smoke_cosys_airsim_runtime.py
```
This will print the multirotor state and save `storage/drone_sim/smoke_frame.png` if successful.

## 6. How Phase 44 will use this
Phase 44 will:
- Connect the Aegis Sentinel backend to this running simulation.
- Capture camera streams using the `front_center` camera.
- Combine drone telemetry (GPS, orientation, velocity) to map it in the 3D web frontend.
- Utilize MAVSDK and `cosysairsim` commands to script drone patrols.

## 7. What remains optional
- **QGroundControl**: Manual installation required. (See `https://qgroundcontrol.com/downloads/`). Not required for basic SimpleFlight visual simulation.
- **PX4/Gazebo**: Heavy software-in-the-loop dependencies not strictly needed for this visual pass.
- **Unreal Source Build**: We are using a prebuilt executable environment. Building the Unreal source from `C:\AegisExternalTools\drone_sim\cosys_airsim\Cosys-AirSim` is not required unless you need custom 3D map environments.
