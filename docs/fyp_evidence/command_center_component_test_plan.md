# Command Center 2.0 — Component Test Plan

## Purpose

This document describes the testing strategy for the Sentinel AI Command Center 2.0 frontend (Phase 47–48), as required for FYP evidence.

## Test Strategy

### Unit/Component Tests (Phase 48)
- Framework: Vitest + React Testing Library
- Environment: jsdom (browser-like, headless)
- Scope: Individual components and navigation structure
- Mocking: All API calls and hook dependencies mocked via vi.mock()

### What We Test

1. **Navigation structure** — correct groups, routes, no forbidden wording in route labels
2. **Shell layout** — renders children, sidebar groups, palette trigger, status bar
3. **Command palette** — route search, drone fusion route, forbidden wording absent
4. **Runtime status strip** — all health states (ok, degraded, critical), drone subsystems, model governance
5. **Review queue** — operator review label, empty state, item types
6. **Drone Operations Hub** — simulated labels, navigation links, permission guard
7. **Drone Fusion Page** — fusion wording, simulated badges, confidence breakdown
8. **Tactical 3D fallback** — R3F mock, fallback render, no asset dependency

### Safe Wording in Tests

Every surface is verified against the safe wording policy:

Allowed (verified present):
- "Possible incident"
- "Possible identity match"
- "Candidate cross-source observation"
- "Simulated drone feed" / "Simulated aerial observation"
- "Operator review required"
- "Evidence-backed hypothesis"
- "Model limitation"

Forbidden (verified absent):
- "suspect confirmed" / "identity confirmed" / "target confirmed"
- "criminal confirmed" / "attacker confirmed" / "guilty"
- "real drone pursuit" / "confirmed threat" / "confirmed terrorist"

### What We Do Not Test

- WebGL rendering (jsdom limitation) — Tactical3DStatusScene tested via fallback only
- Mapbox GL map rendering (jsdom limitation) — MapOperationsPage deferred to E2E
- End-to-end flows (deferred to future Playwright phase)
- Real API responses (all mocked for isolation)
- Real drone simulator connection (simulator not required)

## Running Tests

```bash
cd frontend
npm run test        # Run all tests once
npm run test:watch  # Watch mode
npm run test:ui     # Vitest UI browser
```

## CI Integration

Tests can be integrated into GitHub Actions or similar CI:
```yaml
- run: cd frontend && npm run test
```

## FYP Evidence

This test suite demonstrates:
1. Professional engineering practice (component-level TDD)
2. Safety-critical wording enforcement in automated tests
3. Drone simulation correctly labeled as simulated
4. Operator review requirements enforced in UI
5. System resilience through error boundaries and state components
