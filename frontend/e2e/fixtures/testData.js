/**
 * Seed / demo data for E2E tests.
 *
 * All data here is strictly test/dev scoped.  It must NEVER flow into
 * production paths.  These fixtures are used only when the dev server is
 * running in local/test mode (not in production builds).
 */

export const DEMO_CASE = {
  title: 'E2E Demo Case',
  description: 'Automatically created for E2E smoke tests.',
  priority: 'low',
}

export const DEMO_CAMERA_ID = 'cam_e2e_01'

export const DEMO_CASE_ID = 'e2e-case-001'

/** Routes that must load without auth for public shell tests. */
export const PUBLIC_ROUTES = []

/** Routes that require operator-level auth. */
export const AUTHENTICATED_ROUTES = [
  'dashboard',
  'drone-operations',
  'map-operations',
  'investigation',
  'cases',
  'model-governance',
  'uploaded-video-analysis',
]
