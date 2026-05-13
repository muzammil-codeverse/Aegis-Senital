# Final Defense Execution Checklist — Aegis Sentinel AI

**Date:** 2026-05-13  
**Status: READY FOR DEFENSE**

---

## Pre-Launch (Before Examiner Arrives)

- [ ] Start AirSimNH: `C:\AegisExternalTools\drone_sim\runtime\environments\AirSimNH\AirSimNH\WindowsNoEditor\AirSimNH.exe -windowed -ResX=640 -ResY=480 -NoSound -dx12`
- [ ] Wait for AirSimNH window to show the neighborhood scene (~30-60s)
- [ ] Start backend: from `c:\Sentinal-AI\sentinel-ai-system`, run `.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`
- [ ] Start frontend: from `c:\Sentinal-AI\sentinel-ai-system\frontend`, run `npm run dev -- --port 5173`
- [ ] Open browser: http://localhost:5173
- [ ] Verify drone status shows "connected" in dashboard

## Validation Checks (Run Before Demo)

```powershell
# From c:\Sentinal-AI\sentinel-ai-system
.\.venv\Scripts\python.exe -m scripts.smoke_city_drone_runtime --require-city --strict
.\.venv\Scripts\python.exe -m scripts.smoke_drone_dashboard_apis --with-auth
.\.venv\Scripts\python.exe -m scripts.verify_running_demo_app --backend http://127.0.0.1:8000 --frontend http://localhost:5173
```

All three must return `"status": "ok"`.

## Demo Flow

### 1. Drone Simulation Panel
- Show AirSimNH runtime selected (not Blocks)
- Show live GPS coordinates (latitude, longitude, altitude)
- Show front_center camera frame updating
- Show telemetry: position, velocity, orientation

### 2. Mission Execution
- Click "Start Mission" (or trigger via API)
- Show waypoints being executed
- Show mission events appearing in real time
- Mission completes with success status

### 3. Multi-Source Fusion
- Navigate to `/fusion`
- Show observation candidates across cameras + drone
- Explain: "Candidate cross-source observation — Operator review required"
- Show temporal correlation and confidence scores

### 4. Investigations & Cases
- Navigate to `/investigations`
- Show evidence-backed hypothesis (NOT "confirmed suspect")
- Show "Insufficient data" guard on low-confidence links
- Navigate to `/cases`
- Show case timeline with drone + CCTV events

### 5. Uploaded Video Analysis
- Navigate to `/uploaded-videos`
- Show `demo_crowd_street.mp4` analysis report
- Point out: "Simulated aerial observation" labelling
- Show detection results with operator review flag

### 6. Analytics Overview
- Navigate to `/analytics`
- Show system-wide metrics
- Show detection counts, false positive guards

### 7. GIS Visualisation
- Navigate to `/gis` (if visible)
- Show drone flight path overlay
- Show camera coverage zones

## Examiner Questions — Prepared Answers

**Q: Is this a real drone?**  
A: No. This is a simulated aerial environment using AirSimNH, Microsoft's open-source drone simulator. All data is labelled "Simulated aerial observation" and "Operator review required". No real-world flight is performed.

**Q: How does the system avoid false accusations?**  
A: Multiple safety layers: (1) all identifications are "candidate" observations requiring operator review, (2) fusion requires cross-source corroboration, (3) investigation hypotheses include confidence bounds and "Insufficient data" guards, (4) no automatic enforcement actions exist.

**Q: What is the privacy model?**  
A: Role-based access control (RBAC) with object-level authorization. All detection data is stored with audit logs. The system follows investigative workflow — data is available only to authorized operators.

**Q: What if the simulator crashes?**  
A: The system degrades gracefully. The backend returns `degraded_424` status, dashboard shows "Simulator offline", and all other features (video analysis, case management, GIS) remain fully operational.

## Emergency Fallback

If AirSimNH fails to start:
1. Run Blocks runtime: `C:\AegisExternalTools\drone_sim\runtime\environments\Blocks\Blocks_packaged_Windows_55_33\Windows\Blocks.exe -windowed -ResX=640 -ResY=480 -NoSound -dx12`
2. Note to examiner: "We have a simpler fallback environment running for demonstration — the city environment was validated earlier and the smoke frame is saved at `storage/drone_sim/city_smoke_frame.png`"
3. Proceed with Blocks for mission/telemetry demo
4. Show `city_smoke_frame.png` as evidence of city runtime validation
