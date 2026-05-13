# Frontend Runtime Health Final Audit (2026-05-13)

## Scope
- Reproduced runtime health behavior under authenticated admin session.
- Verified backend health endpoints and authenticated runtime-health API responses.
- Patched frontend runtime health mapping/state handling to reduce degraded/unknown spam.
- Added regression tests and Playwright stability spec.
- Re-ran AirSimNH runtime + mission + dashboard/drone smoke checks.
- Verified uploaded-video workflow with demo media.

## Runtime Health / API Verification
- `GET /health`: `200`
- `GET /openapi.json`: `200` (`257` paths)
- `scripts/smoke_admin_login.py`: pass
  - `auth_storage_mode=cookie`
  - `has_auth_cookie=True`
  - `has_csrf_cookie=True`
  - `bearer_returned=True`
- `scripts/smoke_runtime_health_authenticated.py`: pass
  - `/api/system/health`: `200` with structured keys including `checks`, `generated_at`, runtime domains
  - `/api/system/readiness`: `200` with `ready`, `failures`, `generated_at`
  - `/api/system/liveness`: `200` with `alive`, `status`

## Root Cause Summary
- Runtime health hook treated missing subsystem checks and several API errors as immediate `unknown/degraded` card states, creating noisy UI.
- Auth/permission conditions (especially `403`) were mapped as degraded runtime failure instead of scoped access state.
- Card-level fallback text reused global-style backend outage wording, causing repeated "backend unavailable" messaging.

## Fixes Applied
- `frontend/src/hooks/useRuntimeStatus.js`
  - Added payload normalization (`item` wrapper + status/check extraction).
  - Avoided generating placeholder unknown subsystem cards when checks are absent.
  - Mapped `403` to permission-scoped `unknown` instead of degraded.
  - Mapped network/no-status per-subsystem fallback to `No recent data`.
  - Preserved real critical backend-offline path (`Backend unavailable`) in runtime strip backend section only.
  - Updated no-active mission fallback to `No active mission`.
- `frontend/src/components/command/RuntimeStatusStrip.jsx`
  - Added loading-state message: `Signed in, waiting for runtime status`.
  - Added empty-state message: `No recent data`.
- `frontend/src/api/client.js`
  - Updated generic network fallback message to `Runtime data temporarily unavailable.`
- `frontend/src/api/metricsApi.js`
  - Updated public health fallback wording to `Runtime health temporarily unavailable`.
- `frontend/src/components/common/ErrorState.jsx`
  - Updated default message to `Runtime data temporarily unavailable`.
- Added compatibility export:
  - `frontend/src/api/systemApi.js`

## Tests Added/Updated
- Updated:
  - `frontend/src/hooks/useRuntimeStatus.test.jsx`
  - `frontend/src/components/command/RuntimeStatusStrip.test.jsx`
  - `frontend/src/pages/LoginPage.test.jsx`
- Added:
  - `frontend/src/pages/Dashboard.test.jsx`
  - `frontend/src/api/systemApi.test.js`
  - `frontend/e2e/frontend-runtime-health-stability.spec.js`

## Test Results
- Targeted Vitest suite (runtime/login/dashboard/system API): **pass** (`21/21`).
- Playwright `frontend-runtime-health-stability.spec.js`: **failing** currently due repeated `Backend unavailable` text still present at runtime in live UI route flow; requires one more UI-source trace cycle.

## AirSimNH Mission and Dashboard Validation
- `scripts/launch_city_drone_runtime.py --prefer AirSimNH --windowed --res 960x540`: pass
  - `selected_runtime=AirSimNH`
  - `fallback_used=false`
- `scripts/smoke_city_drone_runtime.py --strict --require-city`: pass
  - `rpc_ok=true`, `telemetry_ok=true`, `front_center_frame_ok=true`
- `scripts/configure_drone_multicamera_settings.py --profile city_demo`: pass
- `scripts/run_city_drone_mission_demo.py --mission fixed_camera_handoff_demo --prefer AirSimNH --device cuda`: completed with warnings
  - `mission_status=completed_with_warnings`
  - `telemetry_points=31`
  - `mission_events=3`
  - `frames_processed=1`
  - `fusion_observation_created=true`
- Dashboard linkage checks:
  - `scripts/smoke_drone_stream_to_dashboard.py --duration 30 --device cuda`: pass
    - telemetry/frame updates and events persisted (`events_persisted_delta=5`)
  - `scripts/smoke_drone_ws_updates.py --duration 20`: pass (polling fallback mode)
  - `scripts/smoke_drone_dashboard_apis.py --with-auth`: pass
  - `scripts/verify_running_demo_app.py --with-drone`: pass

## Demo Video Preparation + Uploaded Video Workflow
- `scripts/prepare_demo_videos.py --max-videos 4 --prefer-small`: timed out during run; partial output produced under `datasets/demo_videos`.
- Available demo files observed:
  - `demo_people_walking.mp4`
  - `demo_crowd_street.mp4`
  - `demo_general_cctv.mp4`
  - `demo_traffic_road.mp4` (0 bytes; needs re-download)
- `scripts/smoke_uploaded_video_workflow.py --video datasets/demo_videos/demo_people_walking.mp4 --device cuda`: pass
  - upload accepted
  - processing completed
  - report generated (`final_status=completed`, `report_ready=True`)

## Safety Wording Check
- No forbidden enforcement wording was introduced in applied source/test/doc changes.
- Existing safe wording expectations preserved.

## Remaining Blockers
- One live UI source still emits repeated `Backend unavailable` text during Playwright route traversal; needs final route-level trace and source patch to fully clear degraded spam regression.
- `prepare_demo_videos.py` timeout and one zero-byte video file (`demo_traffic_road.mp4`) need retry.
