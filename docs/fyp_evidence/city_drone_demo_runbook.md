# City Drone Demo Runbook

## 1) Runtime Preparation
```powershell
.\.venv\Scripts\Activate.ps1
python scripts\download_airsim_city_environment.py --prefer AirSimNH
python scripts\verify_drone_runtime_inventory.py --require-city
```

If strict city verification fails, do not claim city runtime success. Keep Blocks fallback only and continue with explicit degraded labeling.

## 2) Multi-Camera Settings
```powershell
python scripts\configure_drone_multicamera_settings.py --profile city_demo
python scripts\smoke_drone_multicamera_capture.py --require-cameras front_center,front_left,front_right,downward,rear
```

## 3) Runtime Launch and Smoke
```powershell
python scripts\launch_city_drone_runtime.py --prefer AirSimNH --windowed --res 960x540
python scripts\smoke_city_drone_runtime.py --strict --require-city
python scripts\smoke_city_drone_runtime.py --allow-fallback
```

## 4) Mission Demo
```powershell
python scripts\run_city_drone_mission_demo.py --mission fixed_camera_handoff_demo --prefer AirSimNH --device cuda
python scripts\run_city_drone_mission_demo.py --mission fixed_camera_handoff_demo --runtime Blocks --debug --device cuda
```

## 5) Data and Integration Smokes
```powershell
python scripts\seed_city_drone_demo.py --reset-demo-only --city multan
python scripts\check_final_demo_dashboard_data.py
python scripts\smoke_drone_fixed_camera_fusion.py
python scripts\smoke_drone_investigation_path.py
python scripts\smoke_drone_case_evidence.py
python scripts\smoke_drone_analytics.py
```

## 6) Uploaded Video Demo
```powershell
python scripts\prepare_demo_videos.py --max-videos 4 --prefer-small
python scripts\smoke_uploaded_video_workflow.py --video datasets\demo_videos\demo_people_walking.mp4 --device cuda
```

## 7) Full App Launch and Verification
```powershell
python scripts\launch_city_drone_fyp_demo.py --prefer AirSimNH --with-drone --city multan
python scripts\verify_running_demo_app.py --with-drone
```

## 8) Safe Demo Narration
Use:
- Simulated drone feed
- Simulated aerial observation
- Candidate cross-source observation
- Possible movement path
- Operator review required
- Evidence-backed hypothesis
- Demo scenario
- Insufficient data

Never use identity/guilt/target confirmation language.
