# Frontend Performance Hardening — Phase 48

## Overview

Phase 48 introduces route-level code splitting to reduce initial bundle size, preventing Mapbox GL, Three.js, and React Three Fiber from loading eagerly for all users.

## Lazy-Loaded Routes

All heavy pages are wrapped with `React.lazy()` and `<Suspense>`:

| Route | Heavy Dependency | Lazy |
|-------|-----------------|------|
| MapOperationsPage | mapbox-gl | Yes |
| AnalyticsPage | recharts | Yes |
| DroneSimulationPage | drone API surface | Yes |
| DroneMissionPlannerPage | mission planner canvas | Yes |
| DroneFusionPage | fusion correlation surface | Yes |
| DroneOperationsHub | R3F Tactical3DScene | Yes |
| InvestigationWorkspacePage | GIS overlay | Yes |
| ModelGovernancePage | governance API surface | Yes |
| UploadedVideoAnalysisPage | video analysis surface | Yes |

Lightweight pages (Dashboard, AlertsPage, IncidentsPage, CasesPage, LoginPage) remain eagerly loaded.

## Bundle Budget

`scripts/check_frontend_bundle_budget.py` enforces:

| Threshold | Level |
|-----------|-------|
| Single chunk > 750 KB | Warning |
| Single chunk > 1500 KB | Failure |
| Total JS > 3000 KB | Warning |
| Total JS > 6000 KB | Failure |

Run: `python scripts/check_frontend_bundle_budget.py --warn-only`

## Loading Fallback

`PageLoadingFallback` provides a consistent loading skeleton during lazy chunk fetch.

## Hash Routing Compatibility

All lazy routes preserve hash-based navigation (`window.location.hash`). Suspense boundaries do not interfere with hash change events.

## Known Limitations

- Mapbox GL is still bundled when MapOperationsPage loads — dynamic import of mapbox-gl itself requires further refactoring (deferred to Phase 49 if needed)
- Three.js tree-shaking depends on build tool configuration — Vite handles this automatically via ES module imports
