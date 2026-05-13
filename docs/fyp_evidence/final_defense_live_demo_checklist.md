# Final Defense Live Demo Checklist

**Project:** Aegis Sentinel AI System  
**Phase:** 57 — Final Defense Readiness  
**Date:** 2026-05-13

---

## Pre-Demo Startup Sequence

### 1. Start AirSimNH City Runtime
```
C:\AegisExternalTools\drone_sim\runtime\environments\AirSimNH\AirSimNH\WindowsNoEditor\AirSimNH.exe
```
Wait for "Press any key to load settings" — press key. Wait for city to render (~60s).

### 2. Start Backend
```powershell
$env:AEGIS_JWT_SECRET = "phase57-defense-jwt-secret"
$env:AEGIS_BOOTSTRAP_ADMIN_PASSWORD = "ChangeMe123"
cd C:\Sentinal-AI\sentinel-ai-system
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8001 --workers 1
```
Wait for: `Aegis Sentinel startup complete.`

### 3. Start Frontend
```powershell
cd C:\Sentinal-AI\sentinel-ai-system\frontend
npm run dev -- --host 0.0.0.0 --port 5173
```
Wait for: `Local: http://localhost:5173/`

### 4. Verify connectivity
- Backend health: `curl http://127.0.0.1:8001/health` → `{"status":"ok","models_loaded":true,...}`
- Frontend: open `http://127.0.0.1:5173` in browser

---

## Demo Flow Checklist

### Authentication
- [ ] Open `http://127.0.0.1:5173` in Chrome/Edge
- [ ] Login: username=`admin`, password=`ChangeMe123`
- [ ] Confirm dashboard loads with live camera feeds

### Live Drone Monitoring
- [ ] Navigate to Drone Simulation panel
- [ ] Confirm: "Selected runtime: AirSimNH" / "Simulated drone feed"
- [ ] Start mission via dashboard
- [ ] Show telemetry data (position, velocity, altitude)
- [ ] Show aerial frames in real-time

### Threat Detection Pipeline
- [ ] Show StreamProcessor receiving drone frames
- [ ] Show detection events appearing in event feed
- [ ] Show safe wording: "require operator review" label on all events
- [ ] Demonstrate fusion confidence score (e.g., 0.7672)

### Video Upload Analysis
- [ ] Navigate to Uploaded Video Analysis page
- [ ] Click "Select video" → choose an MP4 file
- [ ] Click "Upload selected file"
- [ ] Watch status: `uploaded` → `processing` → `completed`
- [ ] View generated report and events

### Case Management
- [ ] Show case list (10 seeded cases)
- [ ] Open a case → show evidence, notes, status
- [ ] Demonstrate RBAC: analyst can view but not delete

### Analytics
- [ ] Show analytics dashboard with risk scores
- [ ] Show event timeline
- [ ] Demonstrate filtering and export

### Investigation Module
- [ ] Show hypothesis generation
- [ ] Show path reconstruction results
- [ ] Confirm `operator_review_required: true` on all outputs

---

## Safety and Ethics Checks

| Check | Verified |
|---|---|
| All detections labeled as "simulated" | ✓ |
| `operator_review_required: true` on all outputs | ✓ |
| No false certainty language | ✓ |
| Auth enforced on all endpoints | ✓ |
| RBAC prevents unauthorized access | ✓ |
| Audit log captures all sensitive actions | ✓ |

---

## System Specs

| Component | Spec |
|---|---|
| OS | Windows 11 Home 10.0.26200 |
| Python | 3.12 (.venv) |
| GPU | CUDA (RTX-class) |
| Node.js | v20+ |
| Backend port | 8001 |
| Frontend port | 5173 |
| AirSimNH | Local Windows binary |

---

## Credential Reference

| Service | Username | Password |
|---|---|---|
| Aegis Dashboard | admin | ChangeMe123 |

---

## Troubleshooting Quick Reference

**"backend unreachable" in dashboard:**  
→ Check `frontend/.env` has `VITE_API_BASE_URL=http://127.0.0.1:8001` (no BOM)  
→ Restart Vite with `--host 0.0.0.0 --port 5173`

**Upload fails silently:**  
→ Must click "Select video" THEN "Upload selected file" (two-step flow)  
→ Confirm backend is responding at 8001

**AirSimNH "Server too old" warning:**  
→ Safe to ignore — 3-arg `simGetImages` fix is applied in `cosys_airsim_client.py`  
→ Fallback activates automatically if needed

**Port 8000 zombie process:**  
→ Use port 8001 for backend (already configured)  
→ Zombie resolves on full system restart

---

*This checklist covers the complete live demo flow for FYP final defense presentation.*
