# Final UI Runtime Failure Trace (2026-05-13)

## Environment
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Auth mode: cookie (admin login successful)
- Repro pages: `#drone-simulation`, `#uploaded-video-analysis`

## Drone Simulation Repro
- Page: `#drone-simulation`
- Action: Open page, click **Start session**
- Observed network failures: none in this capture window
- Observed API calls: `GET /api/drone-simulation/status`, `GET /api/drone-simulation/runtime-status`, `GET /api/drone-simulation/cameras`, `POST /api/drone-simulation/start`
- Auth/cookie: present (session cookie set after login)
- CSRF: mutating calls include cookie-auth flow; no CSRF rejection observed
- CORS: not observed
- Endpoint mismatch: not observed in this run

## Uploaded Video Repro
- Page: `#uploaded-video-analysis`
- Action: Select and upload `demo_people_walking.mp4`
- Failing request(s):
  1. URL: `GET /api/uploaded-videos/uvs_3f660fc7258b4589/report`
  2. Method: `GET`
  3. Status: `404`
  4. Response JSON:
     - `{"status":"error","detail":"Uploaded-video report for 'uvs_3f660fc7258b4589' not found"}`
  5. Request payload: none
  6. Request headers: standard JSON accept headers; authenticated browser session
  7. Auth cookie/bearer: cookie session active
  8. CSRF required/missing: not applicable (GET)
  9. CORS failed: no
  10. Endpoint path wrong: no (endpoint exists; report not yet generated)
  11. Backend structured error: yes (`status`, `detail`)

## Frontend Generic Error Rendering Sources
- Generic fallback string originates from:
  - `frontend/src/api/client.js` (`normalizeError`)
  - `frontend/src/components/common/ErrorState.jsx`
- Route-level UI where this can mask actionable state:
  - `frontend/src/hooks/useDroneSimulation.js`
  - `frontend/src/hooks/useUploadedVideo.js`
  - `frontend/src/components/uploaded-video/UploadedVideoProcessingPanel.jsx`

## Root Cause From Trace
- Uploaded-video report polling treated expected pre-report `404` as broad runtime failure state in UI context.
- Drone and uploaded-video pages lacked route-scoped, action-scoped status messaging and defaulted to generic fallback paths when downstream calls failed.
