# Exhibition Demo — Final Operator Checklist (Phase 10)

**System:** Aegis Sentinel AI — Bank Robbery Demo  
**Scenario:** `bank_robbery_demo` (12-step deterministic)  
**Audience:** Supervisors, judges, exhibition visitors

---

## Pre-Exhibition Startup (T-15 min)

### 1. Backend

```powershell
# From sentinel-ai-system/backend/
cd "c:\Sentinal-AI\sentinel-ai-system\backend"
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] Backend starts with no import errors
- [ ] `http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] `http://localhost:8000/api/system/preflight` returns all checks passed

### 2. Inference Engine

```powershell
cd "c:\Sentinal-AI\sentinel-ai-system\inference"
python stream/stream_processor.py
```

- [ ] Stream processor starts without crash
- [ ] No `AirSim` required — simulation mode active

### 3. Frontend

```powershell
cd "c:\Sentinal-AI\sentinel-ai-system\frontend"
npm run dev
```

- [ ] Dev server starts at `http://localhost:5173`
- [ ] Dashboard loads without blank screen or 500 errors
- [ ] Login with operator credentials (`admin` / local dev password)
- [ ] Exhibition Demo Panel visible below Command Overview
- [ ] Status badge shows `Not Started` or `Ready`

---

## Pre-Demo Reset (T-5 min)

- [ ] Click **Reset** in Exhibition Demo Panel
- [ ] Status badge changes to `Ready`
- [ ] Alert count: **0**, Incident count: **0**
- [ ] Drone-α indicator: **—** (not assigned)
- [ ] Tracking indicator: **○** (not ready)
- [ ] Runbook opens when **Runbook** button is clicked

---

## Demo Flow (Step Mode — controlled presentation)

| Step | Action | Expected Outcome |
|------|--------|-----------------|
| 0 | Click **Start Demo (Step)** | Status → `Running`, Step 0/12 |
| 1 | Click **Step →** | `person_observed` event fires |
| 2 | Click **Step →** | `suspicious_behavior` escalation |
| 3 | Click **Step →** | `perimeter_breach` detected |
| 4 | Click **Step →** | `weapon_detected` — **Alert created**, alert count ≥ 1 |
| 5 | Click **Step →** | `drone_dispatched` — Drone-α indicator lights up ▲ |
| 6 | Click **Step →** | `drone_observation` — Tracking ● goes green |
| 7–12 | Click **Step →** × remaining | Suspect path tracked, camera handoffs, scenario complete |
| End | Status → `Completed` | Review alerts, incidents, tracking panel |

### Talking Points (per step)

- **Step 1–3:** "The system detects a person and begins behavioral analysis using multi-camera fusion."
- **Step 4:** "Weapon detection triggers an automated alert — no human operator needed to raise the alarm."
- **Step 5:** "A drone is autonomously dispatched to track the suspect."
- **Step 6+:** "The drone feeds real-time observations back; the tracking panel updates live."
- **End:** "The system has generated a complete evidence trail — alerts, incidents, camera handoffs, and a drone route — all from a single automated scenario."

---

## Demo Flow (Auto Mode — timed presentation)

Use when you want hands-free demonstration:

- Click **Start Demo (Auto)** — all steps run automatically with a pause between each
- Monitor the status badge and indicator grid
- Click **Cancel** at any time to stop mid-demo
- Only one Auto-Run runs at a time; a second click returns a 409 error

---

## Fallback Plan (if scenario engine fails)

If the backend returns errors or the scenario engine is unavailable:

1. Click **Fallback Replay** (purple button)
2. A deterministic replay banner appears showing the full 12-step timeline
3. Walk the audience through the pre-computed scenario data
4. No live backend run is required for fallback mode
5. All data is labeled **"Demo Replay Mode"** to distinguish from a live run

---

## Post-Demo Reset

After each demo run:

1. Click **Reset** — session is cleared
2. Alert/incident counts return to 0
3. Session file `runtime_state/exhibition_demo/demo_session.json` is cleared
4. System is ready for the next run immediately

---

## Preflight Verification Commands

```powershell
# Backend health
Invoke-RestMethod http://localhost:8000/health

# Preflight full check
Invoke-RestMethod http://localhost:8000/api/system/preflight

# Exhibition demo status
Invoke-RestMethod http://localhost:8000/api/exhibition-demo/status `
  -Headers @{Authorization = "Bearer <token>"}

# Full backend test suite
cd "c:\Sentinal-AI\sentinel-ai-system"
python -m pytest tests/ -v --tb=short
```

---

## Known Limitations (Phase 10)

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| AirSim not required | None — simulation is deterministic | System works fully without AirSim |
| No real video feed | Demo uses scenario engine events | Show uploaded-video page for recorded analysis |
| Auto-run is synchronous | HTTP request blocks during full run (~10s) | Use Step mode for presentations; auto-run for unattended demos |
| Session survives restart | Stale badge shown after backend restart | Click Reset — session file is cleared |
| Single active demo session | Cannot run two demos simultaneously | By design — reset between runs |

---

## Emergency Talking Points (if things go wrong)

- **Backend crash:** "The system detected an infrastructure issue. In production, this would trigger an automatic failover. Let me show you the Fallback Replay mode." → Click **Fallback Replay**
- **401 error:** "Session token expired — logging back in." → Re-login, then Reset
- **Step returns 409:** "The system correctly prevented a duplicate action — here's the state management at work."
- **Scenario completes early:** "The scenario engine detected all conditions were met and auto-completed. Let me reset and walk through it step by step."

---

## Go / No-Go Checklist

- [ ] Backend running on port 8000
- [ ] Frontend running on port 5173
- [ ] Logged in as operator
- [ ] Exhibition Demo Panel visible on Dashboard
- [ ] Reset returns `Ready` status
- [ ] Start Demo (Step) returns `Running` status
- [ ] Step → advances step counter
- [ ] Weapon event (step 4) creates alert
- [ ] Drone indicator (▲) appears after step 5
- [ ] Tracking indicator (●) appears after step 6
- [ ] Fallback Replay button loads deterministic data
- [ ] Runbook opens with 18+ steps

**All items checked → GO for exhibition.**

---

*Generated for Phase 10 — Exhibition Hardening. Last updated: 2026-05-20.*
