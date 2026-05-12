# Final FYP Demo Runbook — Aegis Sentinel AI

## Purpose

Step-by-step guide for running the Final Year Project defense demonstration.
Follow the steps in order. Each step includes the feature to demonstrate and
the safe wording to use during the presentation.

---

## Pre-Demo Setup (5–10 minutes before)

1. Ensure all dependencies are installed: `.\.venv\Scripts\Activate.ps1`
2. Confirm runtime validation passes:
   ```bash
   python scripts/validate_runtime.py --profile development
   ```
   Expected: `PASSED — all required checks OK`
3. Anomaly live-eval evidence exists:
   ```bash
   python scripts/generate_anomaly_live_eval_summary.py
   ```
4. No syntax errors in code:
   ```bash
   python -m compileall backend inference ml scripts -q
   ```

---

## Step 1 — Start the Backend

```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Start the backend server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Verify:
```bash
curl http://localhost:8000/health
# Expected: {"status": "ok", ...}
```

---

## Step 2 — Start the Frontend

In a new terminal:

```bash
cd frontend
npm run dev
```

Expected output:
```
VITE vX.X.X  ready in NNN ms
  ➜  Local:   http://localhost:5173/
```

Open [http://localhost:5173](http://localhost:5173) in the browser.

---

## Step 3 — Validate Runtime

Show the runtime validation output to the audience:

```bash
python scripts/validate_runtime.py --profile development
```

Highlight:
- PyTorch and Ultralytics YOLO loaded
- InsightFace face recognition available
- Re-ID (torchreid) available
- SAM2 segmentation available
- FAISS vector search available
- All 112+ checks passing

---

## Step 4 — Open Dashboard

Navigate to the Command Center dashboard at `/dashboard`.

Demonstrate:
- Live camera feed simulation (safe wording: **Simulated aerial observation**)
- Detection panels showing operator alerts
- Safe wording on all alerts: **Possible incident** / **Operator review required**
- NOT "Suspect confirmed" or "Target confirmed"

---

## Step 5 — Uploaded Video Workflow

Navigate to the video upload section.

Demonstrate:
1. Upload a short test video
2. Show the uploaded video session being processed
3. Show detection results appearing in real-time
4. Show anomaly scoring with the anomaly detection model
5. Show evidence being logged to the case management system

Safe wording to emphasize:
- **Candidate cross-source observation** (not "confirmed")
- **Model limitation** disclaimer visible in results
- **Insufficient data** shown when confidence is low

---

## Step 6 — GIS Map

Navigate to the GIS Map view.

Demonstrate:
1. Camera locations pinned on the map
2. Heatmap overlay showing incident density
3. Click a camera marker to see live feed preview
4. Show the geofence boundaries
5. Demonstrate investigation path overlay (route between detection events)

Key talking points:
- Spatial correlation across cameras
- No personal location tracking — only camera coverage zones
- Operator must manually trigger any investigation action

---

## Step 7 — Drone Simulation

Navigate to the Drone section.

Demonstrate:
1. **Drone simulation dashboard** — safe wording: **Simulated drone feed**
2. Show drone telemetry in the UI (altitude, heading, speed)
3. Show simulated aerial view panel
4. Show drone status indicators (battery, connection quality)

Emphasize:
- All drone feeds are clearly labeled **Simulated aerial observation**
- No real drone pursuit capability — demonstration system only
- AirSim integration is for simulation training data only

---

## Step 8 — Drone Mission Planner

Navigate to the Drone Mission Planner.

Demonstrate:
1. Create a new patrol mission with waypoints on the map
2. Set mission parameters (altitude, speed, radius)
3. Show the mission route preview on the GIS overlay
4. Show the patrol mission safety constraints (geofence enforcement)

Safe wording on mission plans:
- Mission descriptions use **area monitoring** not **pursuit**
- Waypoints described as **observation points**

---

## Step 9 — Drone Fusion

Navigate to the Drone Fusion view.

Demonstrate:
1. Show cross-source correlation panel
2. Show a fusion observation (drone + fixed camera correlation)
3. Show the fusion confidence score
4. Show the **Candidate cross-source observation** label

Key point: system correlates observations probabilistically — it never confirms identity.

---

## Step 10 — Investigation Path

Navigate to the Investigation section.

Demonstrate:
1. Show an active investigation path reconstruction
2. Show the timeline of detections across cameras
3. Show the hypothesis panel with safe wording: **Evidence-backed hypothesis**
4. Show the operator review trigger button

Emphasize:
- Investigative path is a probabilistic reconstruction
- All conclusions require operator review
- No automated action is taken without human authorization

---

## Step 11 — Case and Evidence Workflow

Navigate to the Case Management section.

Demonstrate:
1. Open an existing case
2. Show evidence attached to the case (video clips, detections)
3. Add a case note
4. Show audit log of all actions on the case
5. Show case export functionality

Safe wording in case records:
- Case type: **Possible incident** (not "confirmed incident")
- Identity references: **Possible identity match** (not "confirmed identity")

---

## Step 12 — LLM-Safe Report Generation

Navigate to the case report generation feature.

Demonstrate:
1. Select a case with evidence
2. Generate an LLM-assisted summary
3. Show the generated report with:
   - Source references cited
   - LLM safety caveats embedded: **Operator review required**
   - No fabricated details beyond the evidence
4. Show the report preview before finalizing

If OpenAI API key is not configured:
- Show the stub/disabled LLM mode message
- Explain that in production, OpenAI GPT-4o-mini or equivalent is used

---

## Step 13 — Model Governance

Navigate to the Model Governance / Registry section.

Demonstrate:
1. Model registry showing all active models with version hashes
2. Drift monitoring metrics for the anomaly detection model
3. Production readiness gate status
4. Model approval workflow (pending → approved → active)

Key talking points:
- No model becomes active without registry approval
- Hash verification prevents unauthorized model substitution
- Drift alerts trigger operator review, not automatic rollback

---

## Step 14 — Analytics Dashboard

Navigate to the Analytics section.

Demonstrate:
1. System metrics (detections per hour, alert rate)
2. Camera coverage analytics
3. Anomaly score distribution chart
4. Identity system calibration status (face / re-ID benchmarks)
5. Case resolution rates

Show the safe wording in analytics labels — aggregate statistics, not individual tracking.

---

## Step 15 — Final Validation Evidence

Open a terminal and run the final evidence sequence:

```bash
# Runtime validation
python scripts/validate_runtime.py --profile development

# Safe wording check
python scripts/check_frontend_safe_wording.py

# Accessibility check
python scripts/check_frontend_accessibility_static.py

# Bundle budget
python scripts/check_frontend_bundle_budget.py --warn-only

# Production readiness (shows honest failures for missing infra)
python scripts/run_production_readiness_validation.py --generate-governance-evidence
```

Show the test suite results:
```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -5
# Expected: 871+ passed, ≤4 skipped
```

Show the anomaly live-eval evidence:
```bash
cat storage/anomaly_live_eval/live_eval_report.md
```

---

## Emergency Fallbacks

| Issue | Fallback |
|---|---|
| Backend fails to start | Check `.env` for `AEGIS_JWT_SECRET`; use development default |
| OpenAI key missing | Set `OPENAI_PROVIDER=disabled` in `configs/runtime/llm.yaml` |
| Database connection fails | System falls back to JSONL storage (development only) |
| Drone simulation unavailable | Demo drone UI in offline/simulation mode |
| AirSim not installed | Drone routes work in simulation-only mode |
| Frontend build fails | Use `npm run dev` for development server |

---

## Safe Wording Reference Card

| Use | Do NOT use |
|---|---|
| Possible incident | Suspect confirmed |
| Possible identity match | Identity confirmed |
| Candidate cross-source observation | Target confirmed |
| Simulated drone feed | Real drone pursuit |
| Simulated aerial observation | Confirmed terrorist |
| Operator review required | Criminal confirmed |
| Evidence-backed hypothesis | Guilty |
| Model limitation | Confirmed threat |
| Insufficient data | Attacker confirmed |

---

## Post-Demo

1. Stop the backend: `Ctrl+C`
2. Stop the frontend dev server: `Ctrl+C`
3. Deactivate venv: `deactivate`
4. Do not commit any generated storage outputs or test videos

Total expected demo time: 25–35 minutes
