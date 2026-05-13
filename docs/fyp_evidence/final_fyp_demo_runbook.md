# Final FYP Demo Runbook - Drone Centered

## Goal
Demonstrate the full local Aegis Sentinel workflow with simulated drone operations, dashboard linkage, seeded demo data, and uploaded-video analysis.

## Pre-Run Validation
```powershell
.\.venv\Scripts\Activate.ps1
python -m compileall backend inference ml scripts -q
python scripts\validate_runtime.py --profile development
python scripts\check_frontend_safe_wording.py
python scripts\check_frontend_accessibility_static.py
python scripts\check_frontend_bundle_budget.py --warn-only
```

## Runtime Validation
```powershell
python scripts\verify_drone_runtime_inventory.py --require-city
python scripts\launch_city_drone_runtime.py --prefer AirSimNH --windowed --res 960x540
python scripts\smoke_city_drone_runtime.py --strict --require-city
```

If strict city validation fails, continue only as fallback demo scenario and state degraded runtime honestly.

## One-Command Local Launch
```powershell
python scripts\launch_city_drone_fyp_demo.py --prefer AirSimNH --with-drone --city multan
python scripts\verify_running_demo_app.py --with-drone
```

## Demo Route Order
1. `/#dashboard`
2. `/#drone-operations`
3. `/#drone-simulation`
4. `/#drone-mission-planner`
5. `/#map-operations`
6. `/#drone-fusion`
7. `/#investigation`
8. `/#cases`
9. `/#uploaded-video-analysis`
10. `/#analytics`
11. `/#model-governance`

## Mission and Pipeline Smoke
```powershell
python scripts\run_city_drone_mission_demo.py --mission fixed_camera_handoff_demo --prefer AirSimNH --device cuda
python scripts\smoke_drone_simulation_pipeline.py --strict --device cuda --duration 30
python scripts\smoke_drone_fixed_camera_fusion.py --live --device cuda
```

## Uploaded Video Verification
```powershell
python scripts\prepare_demo_videos.py --max-videos 4 --prefer-small
python scripts\smoke_uploaded_video_workflow.py --video datasets\demo_videos\demo_people_walking.mp4 --device cuda
```

## Required Safe Wording
- Simulated drone feed
- Simulated aerial observation
- Candidate cross-source observation
- Possible movement path
- Operator review required
- Evidence-backed hypothesis
- Demo scenario
- Insufficient data

## Forbidden Wording
- Suspect confirmed
- Identity confirmed
- Target confirmed
- Criminal confirmed
- Attacker confirmed
- Guilty
- Real drone pursuit
- Confirmed terrorist
- Confirmed threat

## Final Local Readiness Record
Document final evidence in:
- `docs/fyp_evidence/city_drone_simulation_design.md`
- `docs/fyp_evidence/city_drone_demo_runbook.md`
- `docs/fyp_evidence/final_fyp_demo_runbook.md`
- `docs/fyp_evidence/phase55_drone_demo_readiness_report.md`
