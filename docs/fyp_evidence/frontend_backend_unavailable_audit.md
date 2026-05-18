# Frontend/Backend Unavailable Audit (2026-05-13)

## Reproduction
- Backend: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload`
- Frontend: `npm run dev` on `http://localhost:5173`
- Browser capture: Playwright network/console trace on login route

## Captured Failure (Before Fix)
- Failing URL: `GET http://localhost:8000/api/auth/me`
- Request context: login page bootstrap (before user signs in)
- Browser result: `net::ERR_FAILED`
- Console error: `blocked by CORS policy: No 'Access-Control-Allow-Origin' header`
- Effective frontend interpretation: network/backend unavailable (because axios saw no HTTP status)

## Backend Reachability Verification
- `curl http://localhost:8000/health` => `200 OK`
- `curl http://localhost:8000/openapi.json` => `200 OK`
- Conclusion: backend process was reachable; outage messaging was false-positive.

## Root Cause
1. Pre-auth bootstrap called protected endpoint `/api/auth/me` even when no client token/session hint existed.
2. Browser treated the pre-auth request as CORS-failed, which surfaced as a generic network error in frontend.
3. Runtime status parsing promoted network/auth failures into broad “backend unavailable/degraded” wording.
4. Production-style wording (“protected system health endpoint temporarily unavailable”) leaked into local demo UX.

## Fix Summary
1. Added auth bootstrap gating in `frontend/src/hooks/useAuth.js`:
   - In cookie mode with no stored token, skip `getMe()` bootstrap probe and resolve unauthenticated cleanly.
2. Normalized runtime status messaging in `frontend/src/hooks/useRuntimeStatus.js`:
   - `401` => unauthenticated wording (`Sign in to view ...`), not backend-offline.
   - `503`/temporary health probe failure => degraded wording without production panic text.
   - Removed “No health data reported” default from global runtime cards.
3. Added dev-safe API base diagnostic log once:
   - `[Aegis] API base URL: ...` in dev only.
4. Added regression tests:
   - `frontend/src/pages/LoginPage.test.jsx`
   - Extended `frontend/src/hooks/useRuntimeStatus.test.jsx`

## Post-Fix Verification Snapshot
- Login page no longer emits `/api/auth/me` request when unauthenticated.
- No CORS/network spam observed on initial login view.
- Runtime strip wording uses local/demo-safe degraded text.
