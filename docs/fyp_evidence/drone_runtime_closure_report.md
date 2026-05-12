# Drone Runtime Closure Report

Date validated: May 12, 2026

## Summary
- Dependency strict check: PASS
- Blocks runtime path: `C:\AegisExternalTools\drone_sim\runtime\environments\Blocks\Blocks_packaged_Windows_55_33\Windows\Blocks.exe`
- `settings.json`: PASS
- Runtime strict validation: PASS
- Cosys smoke: PASS
- Drone pipeline smoke: PASS
- Mission smoke: PASS
- Fusion live smoke: PASS
- Phase 50 live revalidation against the running Blocks runtime: PASS
- Unresolved blockers: none on the validated setup

## Baseline environment
- Python: `3.12.10`
- Interpreter: repo `.venv`
- CUDA: available on `NVIDIA GeForce RTX 4060 Laptop GPU`
- `pip check`: clean

## Dependency verification
Validated with:

```powershell
python scripts\verify_drone_sim_dependencies.py --strict
```

Verified packages and tools included:
- `cosysairsim`
- `msgpackrpc`
- `pymavlink`
- `mavsdk`
- `geopy`
- `pyproj`
- `shapely`
- `networkx`
- `opencv-python`
- `numpy`
- `pandas`
- `pyyaml`
- `ffmpeg`
- `git-lfs`

## Runtime location and configuration
- Runtime directory:
  `C:\AegisExternalTools\drone_sim\runtime`
- Blocks executable:
  `C:\AegisExternalTools\drone_sim\runtime\environments\Blocks\Blocks_packaged_Windows_55_33\Windows\Blocks.exe`
- AirSim settings file:
  `C:\Users\mufee\Documents\AirSim\settings.json`

Validated settings included:
- `SimMode: Multirotor`
- `Vehicle: Drone1`
- `Camera: front_center`
- `ImageType 0`
- `1280x720`

## Fatal error diagnosis
An actual Unreal Engine fatal error was reproduced earlier in this phase and was not treated as a false positive.

Observed crash evidence:
- Crash folder:
  `C:\AegisExternalTools\drone_sim\runtime\environments\Blocks\Blocks_packaged_Windows_55_33\Windows\Blocks\Saved\Crashes\UECC-Windows-3943F43444C3208C5D282284D73C4BD2_0000`
- Crash type:
  `EXCEPTION_ACCESS_VIOLATION`
- Crash timestamp context:
  runtime log opened on May 12, 2026 at `14:49:56` local time
- Crash context reported primary GPU:
  `Intel(R) UHD Graphics`

This was resolved operationally by:
- launching Blocks in a stable low-overhead profile
- keeping the runtime on the validated host and port
- adding a repo launcher that surfaces the last crash summary instead of failing silently

Stable launch profile:

```powershell
python scripts\launch_blocks_runtime.py
```

Equivalent manual launch:

```powershell
cd C:\AegisExternalTools\drone_sim\runtime\environments\Blocks\Blocks_packaged_Windows_55_33\Windows
.\Blocks.exe -windowed -ResX=640 -ResY=480
```

If the Unreal fatal dialog recurs on another workstation:
1. Launch with the same `-windowed -ResX=640 -ResY=480` profile.
2. Force `Blocks.exe` onto the high-performance GPU in Windows Graphics Settings or NVIDIA Control Panel.
3. Re-run `python scripts\verify_drone_sim_runtime.py --strict` to print the latest crash summary.

## Runtime validation results
Validated with:

```powershell
python scripts\verify_drone_sim_runtime.py --strict
python scripts\smoke_cosys_airsim_runtime.py
python scripts\smoke_drone_simulation_pipeline.py --strict --device cuda
python scripts\smoke_drone_mission.py --strict --device cuda
python scripts\smoke_drone_fixed_camera_fusion.py
python scripts\smoke_drone_fixed_camera_fusion.py --live --device cuda
```

Results:
- RPC connection: OK
- Telemetry retrieval: OK
- RGB frame retrieval from `front_center`: OK
- Smoke frame persisted under `storage/drone_sim/smoke_frame.png`
- Stream processor smoke: OK
- `source_type=drone_simulation`: confirmed
- `simulated=true`: confirmed
- Mission creation and waypoint validation: OK
- Geo-to-NED conversion: OK
- Simulator movement commands: OK
- Telemetry collection during mission: OK
- Mission status progression: OK
- Deterministic fusion smoke: OK
- Live drone plus fixed-camera fusion smoke: OK

## Code-side closure work
Implemented during closure:
- `scripts/launch_blocks_runtime.py`
  Provides a stable launcher and crash-summary reporting.
- `scripts/verify_drone_sim_runtime.py`
  Now prints a direct recovery hint and latest crash summary when the runtime is unavailable.
- `backend/app/services/drone/cosys_airsim_client.py`
  Added named-vehicle fallback handling, environment defaults, and command preparation.
- `backend/app/services/drone/drone_mission_execution_service.py`
  Added real synchronous mission execution against the simulator.
- `scripts/smoke_drone_mission.py`
  Updated to validate real mission execution.
- `scripts/smoke_drone_fixed_camera_fusion.py`
  Updated live mode to use the real simulator-backed drone source.

## Final closure state
The drone runtime closure gate is considered closed on this validated workstation because all mandatory strict runtime commands passed against the prepared Cosys-AirSim Blocks runtime.
