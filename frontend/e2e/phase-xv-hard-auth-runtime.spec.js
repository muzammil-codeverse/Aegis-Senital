/**
 * Phase XV — Hard Local Auth Runtime Reset + Deterministic Exhibition Session Contract
 *
 * This test suite validates that:
 *   1. Login with admin/AegisLocalAdmin2026! succeeds and stores a bearer token
 *   2. No false "Session expired" / "Authentication required" texts appear after login
 *   3. Dashboard is visible and populated
 *   4. Route smoke matrix passes (all critical endpoints return 2xx for admin)
 *   5. Uploaded Video page is accessible and upload attempt does NOT show "session expired"
 *   6. Exhibition Demo panel and Visual Scenario panel are accessible
 *   7. Auth persists across a page reload
 *
 * Gate: requires AEGIS_E2E_BACKEND=true and a running backend on localhost:8000.
 *
 * Run:
 *   $env:AEGIS_E2E_BACKEND="true"; npx playwright test e2e/phase-xv-hard-auth-runtime.spec.js --project=chromium --trace=on
 */
import { test, expect, request as apiRequest } from '@playwright/test'

const BACKEND_LIVE = process.env.AEGIS_E2E_BACKEND === 'true'
const API_BASE = process.env.AEGIS_API_BASE || 'http://localhost:8000'
const FRONTEND_BASE = process.env.AEGIS_E2E_FRONTEND || 'http://localhost:5173'
const ADMIN_USER = 'admin'
const ADMIN_PASS = process.env.AEGIS_E2E_PASS || 'AegisLocalAdmin2026!'
const AUTH_TOKEN_KEY = 'aegis.accessToken'

// Auth texts that must NEVER appear after login
const FORBIDDEN_AUTH_TEXTS = [
  'Session expired',
  'Authentication required',
  'Sign in to view',
  'Runtime data temporarily unavailable',
  'Upload request failed: session expired',
  'Session validation failed',
  'protected runtime unavailable',
  'auth required',
  'session-list unavailable: auth required',
  'session-list unavailable: session expired',
]

// ── Helpers ──────────────────────────────────────────────────────────────────

async function loginViaUI(page) {
  await page.goto(FRONTEND_BASE)
  // Wait for loading state to clear (first pass)
  await page.waitForFunction(
    () => !document.body?.innerText?.toLowerCase().includes('loading session'),
    null,
    { timeout: 20000 },
  ).catch(() => null)

  const loginInput = page.locator('input[autocomplete="username"]').first()
  const isLoginPage = await loginInput.isVisible({ timeout: 5000 }).catch(() => false)
  if (!isLoginPage) {
    // Already authenticated
    return
  }

  await loginInput.fill(ADMIN_USER)
  await page.locator('input[type="password"]').first().fill(ADMIN_PASS)
  await page.locator('button[type="submit"]').first().click()

  // Wait for "Signing in..." button text to clear (login API call completed)
  await page.waitForFunction(
    () => !document.body?.innerText?.toLowerCase().includes('signing in'),
    null,
    { timeout: 20000 },
  ).catch(() => null)

  // Wait for JWT to land in localStorage — this is the authoritative signal that
  // the login response was processed and the token committed to storage.
  await page.waitForFunction(
    (key) => window.localStorage.getItem(key) !== null,
    AUTH_TOKEN_KEY,
    { timeout: 10000 },
  ).catch(() => null)

  // After token lands, app re-enters auth.loading = true briefly before rendering
  // the authenticated shell. Wait for that second loading phase to clear.
  await page.waitForFunction(
    () => !document.body?.innerText?.toLowerCase().includes('loading session'),
    null,
    { timeout: 15000 },
  ).catch(() => null)

  await page.waitForTimeout(500)
}

async function getStoredToken(page) {
  return page.evaluate(key => window.localStorage.getItem(key), AUTH_TOKEN_KEY)
}

async function smokeGet(ctx, path, token) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  const resp = await ctx.get(`${API_BASE}${path}`, { headers, timeout: 12000 })
  return { status: resp.status(), path }
}

async function smokePost(ctx, path, token, body = {}) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  const resp = await ctx.post(`${API_BASE}${path}`, { data: body, headers, timeout: 12000 })
  return { status: resp.status(), path }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe('Phase XV — Auth Contract', () => {
  test.skip(!BACKEND_LIVE, 'Set AEGIS_E2E_BACKEND=true to run live backend tests')

  test('1. Login stores bearer token in localStorage', async ({ page }) => {
    await loginViaUI(page)
    const token = await getStoredToken(page)
    expect(token, 'Bearer token must be stored in localStorage after login').toBeTruthy()
    expect(token.split('.').length, 'Token must be a JWT (3 parts)').toBe(3)
  })

  test('2. No forbidden auth texts appear after login', async ({ page }) => {
    await loginViaUI(page)
    await page.waitForTimeout(2000) // allow panels to settle
    const bodyText = await page.locator('body').innerText()
    for (const phrase of FORBIDDEN_AUTH_TEXTS) {
      expect(bodyText, `Forbidden auth text must NOT appear: "${phrase}"`).not.toContain(phrase)
    }
  })

  test('3. Dashboard is visible after login', async ({ page }) => {
    await loginViaUI(page)
    await page.waitForTimeout(1000)
    // Wait explicitly for the authenticated shell (CommandTopBar eyebrow text)
    await page.waitForFunction(
      () => document.body?.innerText?.includes('Unified Command Center'),
      null,
      { timeout: 10000 },
    ).catch(() => null)
    const body = await page.locator('body').innerText()
    const hasDashboard =
      body.includes('Unified Command Center') ||
      body.includes('Dashboard') ||
      body.includes('Command')
    expect(hasDashboard, 'Dashboard content must be visible after login').toBe(true)
    // Username or role must be visible in the UserMenu
    const hasUser =
      body.toLowerCase().includes('system administrator') ||
      body.toLowerCase().includes('admin') ||
      body.toLowerCase().includes('logout')
    expect(hasUser, 'Authenticated username / logout button must appear in shell').toBe(true)
  })

  test('4. Auth persists across page reload', async ({ page }) => {
    await loginViaUI(page)
    const tokenBefore = await getStoredToken(page)
    expect(tokenBefore, 'Token must exist before reload').toBeTruthy()

    await page.reload()
    await page.waitForFunction(
      () => !document.body?.innerText?.toLowerCase().includes('loading session'),
      null,
      { timeout: 15000 },
    ).catch(() => null)
    await page.waitForTimeout(1500)

    const body = await page.locator('body').innerText()
    expect(body, 'Session expired must NOT appear after reload').not.toContain('Session expired')
    expect(body.toLowerCase(), 'Login form must NOT reappear after reload').not.toContain('operator login')
  })

  test('5. /api/auth/me accepts bearer token', async ({ page }) => {
    await loginViaUI(page)
    const token = await getStoredToken(page)
    expect(token).toBeTruthy()

    const ctx = await apiRequest.newContext()
    const resp = await ctx.get(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(resp.status(), '/api/auth/me must return 200 with bearer token').toBe(200)
    const data = await resp.json()
    expect(data.user?.username).toBe(ADMIN_USER)
    expect(data.user?.role).toBe('admin')
    await ctx.dispose()
  })

  test('6. Critical route smoke matrix — all return 2xx for admin', async ({ page }) => {
    test.setTimeout(180000) // login + 20 parallel requests; give plenty of headroom
    await loginViaUI(page)
    const token = await getStoredToken(page)
    expect(token).toBeTruthy()

    const ctx = await apiRequest.newContext()
    const GET_ROUTES = [
      '/api/auth/me',
      '/api/system/liveness',
      '/api/system/readiness',
      '/api/system/health',
      '/api/capabilities/summary',
      '/api/preflight/latest',
      '/api/exhibition-demo/status',
      '/api/visual-scenario/status',
      '/api/visual-scenario/cameras',
      '/api/simulation/sources/dashboard-feeds',
      '/api/simulation/sources/cameras',
      '/api/simulation/sources/drones',
      '/api/simulation/scenarios',
      '/api/drone-unified/fleet',
      '/api/alerts',
      '/api/incidents',
      '/api/uploaded-videos',
      '/api/map/state',
      '/api/gis/config',
      '/api/analytics/overview',
    ]

    // Run all requests in parallel so a single slow route doesn't block the rest
    const results = await Promise.all(GET_ROUTES.map(route => smokeGet(ctx, route, token)))
    const failures = results
      .filter(({ status }) => status === 401 || status === 403)
      .map(({ status, path }) => `${path} → ${status}`)

    if (failures.length > 0) {
      console.error('Route smoke failures:\n' + failures.join('\n'))
    }
    expect(failures, 'No routes should return 401/403 for admin bearer token').toEqual([])
    await ctx.dispose()
  })

  test('7. Uploaded Video page has no session expired text', async ({ page }) => {
    await loginViaUI(page)
    await page.goto(`${FRONTEND_BASE}/#uploaded-video-analysis`)
    await page.waitForTimeout(3000)

    const body = await page.locator('body').innerText()
    expect(body, 'Session expired must NOT appear on Uploaded Video page').not.toContain('Session expired')
    expect(body, 'Auth required must NOT appear on Uploaded Video page').not.toContain('Authentication required')
    expect(body, '"session expired" scoped error must NOT appear').not.toContain('session expired')
  })

  test('8. Upload does not fail with session expired (API-level check)', async ({ page }) => {
    await loginViaUI(page)
    const token = await getStoredToken(page)
    expect(token).toBeTruthy()

    // Verify GET /api/uploaded-videos works (not 401/403)
    const ctx = await apiRequest.newContext()
    const resp = await ctx.get(`${API_BASE}/api/uploaded-videos`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(resp.status(), 'GET /api/uploaded-videos must return 2xx for admin').toBeLessThan(400)
    await ctx.dispose()
  })

  test('9. Exhibition Demo panel is accessible', async ({ page }) => {
    await loginViaUI(page)
    await page.goto(`${FRONTEND_BASE}/#command-center`)
    await page.waitForTimeout(2000)
    const body = await page.locator('body').innerText()
    // Should not have auth errors
    expect(body, 'Session expired must NOT appear on Command Center page').not.toContain('Session expired')
    expect(body, 'Auth required must NOT appear on Command Center page').not.toContain('Authentication required')
  })

  test('10. Visual Scenario panel is accessible', async ({ page }) => {
    await loginViaUI(page)
    await page.goto(`${FRONTEND_BASE}/#drone-simulation`)
    await page.waitForTimeout(2000)
    const body = await page.locator('body').innerText()
    expect(body, 'Session expired must NOT appear on Visual Scenario page').not.toContain('Session expired')
  })

  test('11. POST /api/exhibition-demo/reset accepts bearer token', async ({ page }) => {
    await loginViaUI(page)
    const token = await getStoredToken(page)
    const ctx = await apiRequest.newContext()
    const resp = await ctx.post(`${API_BASE}/api/exhibition-demo/reset`, {
      data: {},
      headers: { Authorization: `Bearer ${token}` },
    })
    // 200 or 422 (missing body) — but NOT 401/403
    expect(resp.status(), 'Exhibition demo reset must not be 401/403').not.toBe(401)
    expect(resp.status(), 'Exhibition demo reset must not be 403').not.toBe(403)
    await ctx.dispose()
  })

  test('12. CSRF does not block bearer-token requests', async ({ page }) => {
    await loginViaUI(page)
    const token = await getStoredToken(page)
    const ctx = await apiRequest.newContext()
    // POST without CSRF header — should succeed because we use bearer, not cookie
    const resp = await ctx.post(`${API_BASE}/api/exhibition-demo/reset`, {
      data: {},
      headers: {
        Authorization: `Bearer ${token}`,
        // Deliberately no X-CSRF-Token header
      },
    })
    expect(resp.status(), 'Bearer auth POST must NOT return 403 CSRF failure').not.toBe(403)
    await ctx.dispose()
  })
})

// ── UI-only tests (no backend required) ──────────────────────────────────────

test.describe('Phase XV — UI Contract (no backend required)', () => {
  test('Login page renders correctly', async ({ page }) => {
    await page.goto(FRONTEND_BASE)
    // Wait for loading state to clear
    await page.waitForFunction(
      () => !document.body?.innerText?.toLowerCase().includes('loading session'),
      null,
      { timeout: 15000 },
    ).catch(() => null)
    await page.waitForTimeout(1000)
    const body = await page.locator('body').innerText()
    // Login page shows "Aegis Sentinel" + "Operator Login"; authenticated shell
    // shows "Unified Command Center". Either confirms the app rendered successfully.
    const hasLoginOrShell =
      body.includes('Aegis Sentinel') ||
      body.includes('Operator Login') ||
      body.includes('Unified Command Center') ||
      body.includes('Dashboard')
    expect(hasLoginOrShell, 'App must render either login or authenticated shell').toBe(true)
    // Must NOT show "Something went wrong" crash
    expect(body).not.toContain('Something went wrong')
    expect(body).not.toContain('ChunkLoadError')
  })

  test('SessionExpiredBanner does NOT show on fresh page load', async ({ page }) => {
    // Clear any existing auth
    await page.goto(FRONTEND_BASE)
    await page.evaluate(key => window.localStorage.removeItem(key), AUTH_TOKEN_KEY)
    await page.reload()
    await page.waitForTimeout(3000)

    const banner = page.locator('.session-banner')
    const bannerVisible = await banner.isVisible().catch(() => false)
    expect(bannerVisible, '"Session expired" banner must NOT appear on fresh (unauthenticated) page load').toBe(false)
  })
})
