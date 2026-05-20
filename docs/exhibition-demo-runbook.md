# Exhibition Demo Runbook — Bank Robbery / Suspect Escape

**Platform:** Aegis / Drone-S Intelligent Surveillance Command Center  
**Phase:** 9 — Final Exhibition Operator Workflow  
**Demo:** Bank Robbery Demo (`bank_robbery_demo`)

---

## Overview

This runbook describes how to run the deterministic Bank Robbery exhibition demo
from end to end. The demo is designed to be repeatable, professional, and does
not require AirSim, GPU hardware, or an OpenAI key.

---

## Startup Commands

### 1. Start the backend

```bash
# From the project root
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Start the frontend

```bash
cd frontend
npm run dev
# Serves at http://localhost:5173
```

### 3. Verify both are healthy

```
GET http://localhost:8000/api/health
```

Expected: `{"status": "ok"}` or similar.

---

## Login

Navigate to `http://localhost:5173` and log in as:

- **Role:** admin or operator  
- **Credentials:** configured in `configs/auth.yaml` (default in dev-guidelines.md)

Admin credentials are required for POST actions (start, step, reset).

---

## Exhibition Preflight

Before starting the demo, run Exhibition Preflight to verify all core capabilities:

1. Open the **Dashboard**.
2. Locate the **Exhibition Demo Panel** at the top of the dashboard.
3. Click **Runbook** to review steps (optional).
4. Use the **System Health** page or the dedicated preflight button to run Exhibition Preflight.
5. Confirm: no blocking failures.

Via API:

```bash
POST http://localhost:8000/api/preflight/run
{"mode": "EXHIBITION"}
```

If preflight fails, resolve the blocking capabilities before proceeding.

---

## Demo Steps

### Step 1 — Start Bank Robbery Demo

**UI:** Click **"Start Demo (Step)"** in the Exhibition Demo Panel.

**API:**
```bash
POST http://localhost:8000/api/exhibition-demo/start
{"mode": "step", "run_preflight": false}
```

**Expected:** Demo status changes to `running`. Scenario run ID appears.

---

### Step 2 — Routine Surveillance (Step 0)

**UI:** Click **"Step →"**.

**What happens:** Suspicious individual enters Financial District. Camera: `CAM-BANK-01`. Severity: low.

**Narration:** "Our city-wide CCTV network covers 16 cameras across 10 zones. AI is continuously monitoring for anomalies."

---

### Step 3 — Suspicious Behaviour (Step 1)

**UI:** Click **"Step →"**.

**What happens:** Suspect loiters near bank entrance. Behaviour flagged as medium severity.

**Narration:** "The system detects unusual loitering behaviour and flags it for operator review."

---

### Step 4 — Civilian Group (Step 2)

**UI:** Click **"Step →"**.

**What happens:** Group of 5 civilians observed entering bank (`CAM-BANK-02`).

---

### Step 5 — CRITICAL: Weapon Detected (Step 3)

**UI:** Click **"Step →"**.

**What happens:**
- CRITICAL severity event fired
- Alert created and promoted to dashboard
- Incident opened
- DRONE-ALPHA dispatched automatically

**[PAUSE HERE FOR EXHIBITION]**

Show the audience:
1. Critical alert badge in the demo panel (Alerts count increases)
2. Incident counter (Incidents count increases)
3. DRONE-ALPHA indicator turns blue (▲)
4. Click **"View Alerts"** to show the alert detail
5. Click **"View Incidents"** to show the open incident

**Narration:** "Weapon detection at critical confidence has triggered an automatic drone dispatch and opened an incident case."

---

### Step 6 — Security Response (Step 4)

**UI:** Click **"Step →"**.

**What happens:** Bank lockdown. Security guard responds (`CAM-BANK-02`).

---

### Step 7 — DRONE-ALPHA Airborne (Step 5)

**UI:** Click **"Step →"**.

**What happens:** Drone aerial surveillance of Financial District begins.

**Narration:** "DRONE-ALPHA is now airborne with an automated patrol vector covering the incident area."

Show: Click **"View Tracking"** link → Scroll to Operational Tracking Panel → Show drone route waypoints.

---

### Steps 8–11 — Escape Sequence

Continue stepping through:
- Step 6: Suspect moves to parking lot (`CAM-PARKING-01`)
- Step 7: Escape vehicle detected in restricted zone
- Step 8: Suspect enters alley (`CAM-ALLEY-01`)
- Step 9: DRONE-ALPHA aerial confirmation of suspect location

Show: **Camera Handoff Timeline** — 7 camera handoffs tracking suspect from bank to road.

Show: **Suspect Path Map** — waypoints from `zone_financial` → `zone_alley` → `zone_roads`.

---

### Step 12 — Road Checkpoint (Step 10)

**UI:** Click **"Step →"**.

**What happens:** Suspect reaches road checkpoint. Intercept recommended.

---

### Step 13 — Scenario Complete (Step 11)

**UI:** Click **"Step →"**.

**What happens:** Full observation timeline captured. Scenario status: `completed`.

---

### Step 14 — Evidence and Report Review

In the Exhibition Demo Panel:
- **Scenario Evidence Summary** card appears showing:
  - Scenario ID: `bank_robbery_demo`
  - Run ID
  - 2 alerts, 2 incidents
  - 8 source cameras
  - DRONE-ALPHA assigned
  - Disclaimer: all data is simulated

Navigate to:
- `/analytics` — view threat counters updated by scenario
- `/alerts` — view promoted critical alert
- `/incidents` — view open bank robbery incident

---

### Step 15 (Optional) — Uploaded-Video Analysis

Navigate to `/uploaded-video-analysis` and upload any short video clip to
demonstrate ML-based video intelligence (requires model files).

---

## Reset

After the demo:

1. Click **"Reset"** in the Exhibition Demo Panel.
2. Demo status returns to `ready`.
3. Scenario run is cancelled and cleared.
4. Ready for next run.

API:
```bash
POST http://localhost:8000/api/exhibition-demo/reset
```

---

## Auto-Run Mode

For unattended or timed demos:

```bash
POST http://localhost:8000/api/exhibition-demo/start
{"mode": "auto", "run_preflight": false}
```

This runs all 12 steps immediately. Then review the full snapshot:

```bash
GET http://localhost:8000/api/exhibition-demo/snapshot
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/exhibition-demo/status` | GET | Current demo session status |
| `/api/exhibition-demo/reset` | POST | Reset demo state |
| `/api/exhibition-demo/start` | POST | Start demo (mode: step or auto) |
| `/api/exhibition-demo/step` | POST | Advance one scenario step |
| `/api/exhibition-demo/auto-run` | POST | Run remaining steps automatically |
| `/api/exhibition-demo/cancel` | POST | Cancel active demo |
| `/api/exhibition-demo/snapshot` | GET | Full operator snapshot |
| `/api/exhibition-demo/runbook` | GET | Structured runbook steps |

All POST endpoints require `operator:write` permission. GET endpoints require `system:read`.

---

## Troubleshooting

| Symptom | Resolution |
|---|---|
| Demo status `failed` | Check `last_error` in status. Reset and restart. |
| No alerts appearing | Check `runtime_state/scenario_promotions/`. Confirm step 4 (weapon_detected) was executed. |
| Drone not dispatched | Must step through Step 4 (weapon detection) first. |
| Frontend 401 Unauthorized | Token expired. Re-login as admin/operator. |
| Preflight blocking failure | Navigate to System Health. Resolve the blocking capability. |
| Scenario stuck / won't start | Another run may be active. POST `/api/exhibition-demo/reset` then start again. |
| Tracking panel empty | Navigate to `/#operational-tracking`. Tracking populates after Step 4+. |

---

## Known Limitations

- Drone video feed is **simulated** — no live AirSim connection required.
- ML detection is **deterministic** during scenario — uses predefined event timeline.
- LLM/OSINT features are **disabled** unless `OPENAI_API_KEY` is configured.
- Uploaded-video ML inference requires model weight files to be present.
- Analytics counters reflect promotions from the scenario; real CCTV events may vary.

---

## What to Avoid

- Do NOT run destructive database migrations during an exhibition.
- Do NOT start heavy GPU benchmark suites.
- Do NOT download model files during live demo.
- Do NOT expose OpenAI API keys in frontend.

---

## Phase 9 Demo Acceptance Verification

Confirm the following before exhibition:

- [ ] Backend starts cleanly (`uvicorn` with no import errors)
- [ ] Frontend builds and serves correctly (`npm run dev`)
- [ ] Login succeeds for admin/operator
- [ ] Dashboard loads with Exhibition Demo Panel visible
- [ ] Preflight completes with no blocking failures
- [ ] Start Demo creates scenario run
- [ ] Step 4 (weapon_detected) creates 1+ alerts and incidents
- [ ] DRONE-ALPHA indicator activates in demo panel
- [ ] Tracking panel shows suspect path
- [ ] Camera handoff timeline shows 7 handoffs
- [ ] Drone route panel shows DRONE-ALPHA waypoints
- [ ] Fused track shows combined CCTV + drone path
- [ ] Report/evidence summary appears in demo panel
- [ ] Analytics page shows updated counters
- [ ] Reset clears demo cleanly
