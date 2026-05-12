# Phase 49 — Frontend Golden Path Test Plan

## Overview

This document describes the browser-level E2E golden-path workflows validated
in Phase 49 using Playwright.  All tests run against the local dev server
(`http://localhost:5173`) using Chromium.

## Test Infrastructure

| Component | Path | Purpose |
|-----------|------|---------|
| Config | `frontend/playwright.config.js` | Playwright base config, webServer, retries |
| Auth util | `frontend/e2e/utils/auth.js` | Login flow via real UI form |
| Navigation util | `frontend/e2e/utils/navigation.js` | Route navigation and command palette |
| Assertions util | `frontend/e2e/utils/assertions.js` | Safety invariant assertions (forbidden wording, page loaded, empty states) |
| Fixtures | `frontend/e2e/fixtures/testData.js` | Test/dev-only seed data |

## Golden Path Workflows

### 1. Operator Login and Navigation
**File:** `command-center.spec.js`
1. Dev server starts (webServer config)
2. Playwright opens `http://localhost:5173`
3. Login page detected → login with dev credentials
4. App shell renders with sidebar and runtime status strip
5. Ctrl+K opens command palette
6. Type "drone" → results appear
7. All core routes load without crash

### 2. Drone Operations Workflow
**File:** `drone-operations.spec.js`
1. Navigate to `#drone-operations`
2. Verify simulated-drone wording present
3. Verify links to simulation/mission/fusion sub-routes
4. Verify honest offline state (no fake connected status)
5. Navigate to `#drone-simulation` → loads
6. Navigate to `#drone-mission-planner` → loads
7. Navigate to `#drone-fusion` → loads
8. No forbidden wording at any step

### 3. Map Operations Workflow
**File:** `map-operations.spec.js`
1. Navigate to `#map-operations`
2. local_mock provider renders (no Mapbox token needed)
3. Layer controls visible
4. No token error displayed
5. Page stable with empty data

### 4. Investigation Workflow
**File:** `investigation.spec.js`
1. Navigate to `#investigation`
2. Safe wording indicator visible
3. Path reconstruction panel visible
4. "possible" / "evidence-backed" language confirmed
5. "confirmed" language verified absent

### 5. Drone Fusion Workflow
**File:** `drone-fusion.spec.js`
1. Navigate to `#drone-fusion`
2. "Candidate cross-source" or "Simulated" wording visible
3. Review state or honest empty state visible
4. Case ID filter input accessible

### 6. Cases and Evidence Workflow
**File:** `cases.spec.js`
1. Navigate to `#cases`
2. Case list or honest empty state
3. Search input accessible (`aria-label="Search cases"`)
4. If cases exist: click row → drawer opens

### 7. Model Governance Workflow
**File:** `model-governance.spec.js`
1. Navigate to `#model-governance`
2. Model registry visible
3. Drift/limitation section visible
4. Model ID input accessible

### 8. Uploaded Video Workflow
**File:** `uploaded-video.spec.js`
1. Navigate to `#uploaded-video-analysis`
2. Upload dropzone visible
3. Format validation messaging visible
4. Operator review wording visible

### 9. Tactical 3D Browser Safety
**File:** `tactical-3d.spec.js`
1. Dashboard loads without JS crash
2. Drone operations loads without JS crash
3. Canvas or CSS fallback renders
4. No forbidden wording

## Safety Invariants Checked on Every Route

The `assertNoForbiddenWording` assertion runs on every major page and verifies
that NONE of these phrases appear:
- "Suspect confirmed"
- "Identity confirmed"
- "Target confirmed"
- "Criminal confirmed"
- "Attacker confirmed"
- "Confirmed terrorist"
- "Confirmed threat"
- "Real drone pursuit"
- "Guilty"

## Local Execution

```bash
cd frontend
npm run e2e          # headless Chromium
npm run e2e:headed   # visible browser
npm run e2e:report   # show HTML report
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AEGIS_E2E_USER` | `admin` | Login username |
| `AEGIS_E2E_PASS` | `admin` | Login password |
| `AEGIS_E2E_LIVE_DRONE` | `false` | Enable live drone tests |

## CI Integration

Set `CI=true` to enable:
- 1 retry on failure
- Single worker
- Strict forbid-only mode
