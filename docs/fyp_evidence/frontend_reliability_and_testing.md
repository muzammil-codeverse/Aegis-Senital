# Frontend Reliability and Testing — Phase 48

## Overview

Phase 48 adds a comprehensive component test suite to the Sentinel AI Command Center 2.0 frontend, establishing test-driven reliability guarantees for all major UI surfaces.

## Test Framework

- **Vitest 4.x** with jsdom environment
- **React Testing Library** for component rendering
- **@testing-library/jest-dom** for extended matchers
- **@testing-library/user-event** for interaction simulation

## Tested Components

| Component | Test File | Tests |
|-----------|-----------|-------|
| Command Navigation | commandNavigation.test.js | 6 |
| CommandCenterShell | CommandCenterShell.test.jsx | 3 |
| CommandSidebar | CommandSidebar.test.jsx | 5 |
| CommandTopBar | CommandTopBar.test.jsx | 6 |
| CommandStatusBar | CommandStatusBar.test.jsx | 5 |
| CommandPalette | CommandPalette.test.jsx | 7 |
| RuntimeStatusStrip | RuntimeStatusStrip.test.jsx | 10 |
| ReviewQueuePanel | ReviewQueuePanel.test.jsx | 5 |
| DroneOperationsHub | DroneOperationsHub.test.jsx | 8 |
| DroneFusionPage | DroneFusionPage.test.jsx | 12 |
| Tactical3DStatusScene | Tactical3DStatusScene.test.jsx | 6 |

**Total: 73+ tests**

## Safe Wording Enforcement

All tests verify:
- "Simulated aerial observation" and "Simulated drone feed" labels present where required
- "Operator review required" labels present in drone/fusion/review surfaces
- "Candidate cross-source observation" in fusion correlation panels
- "Evidence-backed hypothesis" in investigation surfaces
- No forbidden wording: "suspect confirmed", "identity confirmed", "target confirmed", "criminal confirmed", "attacker confirmed", "guilty", "real drone pursuit", "confirmed threat", "confirmed terrorist"

## Error Boundary

`CommandErrorBoundary` wraps all route content:
- User-friendly error panel (no raw stack traces in UI)
- Error ID + timestamp for support reference
- Try again / Reload page actions

## State Components

Shared state components in `src/components/common/`:
- `LoadingState` — consistent loading UI with role="status"
- `EmptyState` — honest empty state messaging
- `ErrorState` — backend unavailable with retry action
- `PermissionDeniedState` — access denied without leaking object names

## Known Limitations

- WebGL (Three.js / React Three Fiber) cannot be tested in jsdom — Tactical3DStatusScene tests mock R3F and verify fallback rendering only
- Mapbox GL cannot render maps in jsdom — MapOperationsPage tests are not included in this phase
- E2E tests (Playwright/Cypress) are deferred to a future phase
