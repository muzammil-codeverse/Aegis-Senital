# Phase 49 — E2E Validation Summary

## What E2E Tests Cover

### Command Center Shell (`command-center.spec.js`)
- App loads without crash
- Sidebar navigation groups visible
- Runtime status strip visible
- Ctrl+K opens command palette
- Command palette search works
- All core route hashes load (#dashboard, #drone-operations, #map-operations, #investigation, #cases, #model-governance)
- No forbidden wording on any route

### Drone Operations (`drone-operations.spec.js`)
- #drone-operations loads
- Simulated drone wording present
- Links to drone-simulation sub-route
- Disconnected/offline simulator state handled honestly
- Sub-routes: #drone-simulation, #drone-mission-planner, #drone-fusion all load
- Optional live drone tests gated behind `AEGIS_E2E_LIVE_DRONE=true`

### Map / GIS (`map-operations.spec.js`)
- #map-operations loads without Mapbox token (local_mock provider)
- Map container or fallback renders without crashing
- Layer controls or map toolbar visible
- No "Missing Mapbox token" error in local_mock mode
- Page stable with empty data

### Investigation (`investigation.spec.js`)
- #investigation loads
- Safe wording banner/indicator visible
- Path reconstruction panel visible
- Confidence breakdown area visible
- Wording uses "possible/evidence-backed" language, never "confirmed"
- No forbidden wording

### Drone Fusion (`drone-fusion.spec.js`)
- #drone-fusion loads
- "Candidate cross-source" or "Simulated" wording present
- Confidence breakdown or honest empty state
- Review state visible
- Filter by case ID input accessible
- No forbidden wording

### Cases / Evidence (`cases.spec.js`)
- #cases loads
- Case list or honest empty state
- Search cases input accessible (aria-label)
- Case creation form has accessible inputs
- LLM/safety caveat visible
- Case drawer interaction tested (if cases exist)
- No forbidden wording

### Model Governance (`model-governance.spec.js`)
- #model-governance loads
- Model registry section visible
- Model limitations/drift section visible
- Production blockers shown honestly
- Model ID input accessible
- No forbidden wording

### Uploaded Video (`uploaded-video.spec.js`)
- #uploaded-video-analysis loads
- Upload dropzone visible
- File input accessible
- Format/validation messaging visible
- Operator review wording visible
- No forbidden wording

### Tactical 3D Browser Test (`tactical-3d.spec.js`)
- Dashboard loads without JS crash
- Drone operations loads without JS crash
- 3D canvas or fallback container renders (WebGL or CSS fallback)
- No forbidden wording

## What E2E Tests Do NOT Cover

- Full backend integration with real database (tests run against dev server)
- Live Cosys-AirSim drone (gated behind `AEGIS_E2E_LIVE_DRONE=true`)
- Real Mapbox tile rendering (uses local_mock provider)
- Evidence chain-of-custody cryptographic verification (covered by unit tests)
- RBAC enforcement at the API layer (covered by backend auth tests)
- Performance benchmarking (covered by bundle budget checker)
- Full LLM generation quality (covered by LLM safety tests)

## Auth Strategy

Tests exercise the real login form using dev credentials (`admin`/`admin` by default,
configurable via `AEGIS_E2E_USER`/`AEGIS_E2E_PASS` env vars).

No production auth bypass was introduced. No test-mode shortcut was added.

## Local Mock Map Strategy

All E2E tests use `local_mock` map provider (no Mapbox token required). The
`MapProviderCanvas` component falls back to a local SVG grid map when no
`VITE_MAPBOX_TOKEN` is set, displaying a clear banner:
"Mapbox provider: VITE_MAPBOX_TOKEN not set — using local mock".

## Live Drone Test Strategy

Drone telemetry and fusion live tests are skipped by default. Set
`AEGIS_E2E_LIVE_DRONE=true` to enable them when Cosys-AirSim / Blocks is running.

## FYP Demo Workflows Validated

1. Operator logs in → command palette search → navigates to drone operations
2. Drone operations page shows simulated-source labels
3. Map page loads with local mock — no token error
4. Investigation page shows safe wording, path reconstruction UI
5. Cases page shows list or honest empty state, accessible search
6. Model governance shows model registry and drift controls
7. Uploaded video shows dropzone and operator review language
8. No forbidden wording on any page at any time
