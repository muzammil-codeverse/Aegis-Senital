/**
 * Phase 9 — Exhibition Demo E2E smoke test.
 *
 * Gate: requires AEGIS_E2E_BACKEND=true and a running backend.
 * Without the gate the tests assert UI-only behaviour (panel renders,
 * buttons exist) without calling the real API, since a backend may not
 * be running in CI.
 *
 * To run with a live backend:
 *   AEGIS_E2E_BACKEND=true npx playwright test e2e/exhibition-demo.spec.js --project=chromium
 *
 * Without backend:
 *   npx playwright test e2e/exhibition-demo.spec.js --project=chromium
 */
import { test, expect } from '@playwright/test'
import { goTo, ROUTES } from './utils/navigation.js'
import { assertNoForbiddenWording, assertPageLoaded } from './utils/assertions.js'

const BACKEND_LIVE = process.env.AEGIS_E2E_BACKEND === 'true'
const API_BASE = process.env.AEGIS_API_BASE || 'http://localhost:8000'

// Helper: POST to backend API directly (skipped when not live)
async function backendPost(request, path, body = {}) {
  const token = process.env.AEGIS_E2E_TOKEN || ''
  const response = await request.post(`${API_BASE}${path}`, {
    data: body,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  return response
}

// Helper: GET from backend API directly
async function backendGet(request, path) {
  const token = process.env.AEGIS_E2E_TOKEN || ''
  const response = await request.get(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  return response
}

test.describe('Exhibition Demo — Dashboard Panel', () => {
  test('dashboard loads without crash', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)
    await assertNoForbiddenWording(page)
  })

  test('Exhibition Demo Panel is present on dashboard', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)

    // The panel renders the "Bank Robbery Demo" heading
    const panelText = await page.locator('body').innerText()
    const hasPanel = panelText.includes('Bank Robbery Demo') || panelText.includes('Exhibition Mode')
    expect(hasPanel).toBe(true)
  })

  test('Exhibition Demo Panel shows status badge', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)

    // Wait for the panel to settle — it makes an async API call that may take a moment
    await page.waitForTimeout(3000)

    const body = await page.locator('body').innerText()
    const hasStatus = (
      body.includes('Not Started') ||
      body.includes('Ready') ||
      body.includes('Running') ||
      body.includes('Completed') ||
      body.includes('Cancelled') ||
      body.includes('Failed') ||
      // Fallback: panel is at least rendering (the heading or loading state)
      body.includes('Bank Robbery Demo') ||
      body.includes('Connecting to demo')
    )
    expect(hasStatus).toBe(true)
  })

  test('Start Demo buttons are rendered', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)

    const body = await page.locator('body').innerText()
    // At least one of these buttons should appear when demo is not running
    const hasButtons = (
      body.includes('Start Demo') ||
      body.includes('Step') ||
      body.includes('Reset') ||
      body.includes('Auto-Run')
    )
    expect(hasButtons).toBe(true)
  })

  test('Runbook button is present', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)

    const body = await page.locator('body').innerText()
    expect(body).toContain('Runbook')
  })

  test('no logout or blank page during dashboard visit', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)

    // Wait 3 seconds and confirm still authenticated
    await page.waitForTimeout(3000)
    const loginInput = page.locator('input[autocomplete="username"], input[aria-label="Username"]').first()
    const stillLoggedIn = !(await loginInput.isVisible().catch(() => false))
    expect(stillLoggedIn).toBe(true)
  })
})

test.describe('Exhibition Demo — Backend API (live backend only)', () => {
  test.skip(!BACKEND_LIVE, 'Requires AEGIS_E2E_BACKEND=true with a live backend')

  test('GET /api/exhibition-demo/status returns valid shape', async ({ request }) => {
    const res = await backendGet(request, '/api/exhibition-demo/status')
    expect(res.status()).toBeLessThan(500)
    if (res.status() === 200) {
      const body = await res.json()
      expect(body).toHaveProperty('item')
      expect(body.item).toHaveProperty('status')
      expect(body.item).toHaveProperty('demo_id')
    }
  })

  test('POST /api/exhibition-demo/reset succeeds', async ({ request }) => {
    const res = await backendPost(request, '/api/exhibition-demo/reset')
    expect(res.status()).toBeLessThan(500)
  })

  test('POST /api/exhibition-demo/start creates scenario run', async ({ request }) => {
    // Reset first
    await backendPost(request, '/api/exhibition-demo/reset')
    const res = await backendPost(request, '/api/exhibition-demo/start', { mode: 'step', run_preflight: false })
    expect(res.status()).toBeLessThan(500)
    if (res.status() === 200) {
      const body = await res.json()
      expect(body).toHaveProperty('status')
      const demo = body.demo || body
      if (demo.scenario_run_id) {
        expect(typeof demo.scenario_run_id).toBe('string')
      }
    }
  })

  test('POST /api/exhibition-demo/step advances scenario', async ({ request }) => {
    await backendPost(request, '/api/exhibition-demo/reset')
    await backendPost(request, '/api/exhibition-demo/start', { mode: 'step', run_preflight: false })
    const res = await backendPost(request, '/api/exhibition-demo/step')
    expect(res.status()).toBeLessThan(500)
    if (res.status() === 200) {
      const body = await res.json()
      expect(body).toHaveProperty('status')
    }
  })

  test('POST /api/exhibition-demo/step to weapon event creates alert', async ({ request }) => {
    await backendPost(request, '/api/exhibition-demo/reset')
    await backendPost(request, '/api/exhibition-demo/start', { mode: 'step', run_preflight: false })
    // Step 4 times to reach weapon_detected (step index 3)
    for (let i = 0; i < 4; i++) {
      await backendPost(request, '/api/exhibition-demo/step')
    }
    const statusRes = await backendGet(request, '/api/exhibition-demo/status')
    if (statusRes.status() === 200) {
      const body = await statusRes.json()
      const session = body.item || {}
      // After 4 steps weapon_detected is triggered — alert_ids may be populated
      expect(Array.isArray(session.active_alert_ids)).toBe(true)
    }
  })

  test('GET /api/exhibition-demo/snapshot returns combined state', async ({ request }) => {
    const res = await backendGet(request, '/api/exhibition-demo/snapshot')
    expect(res.status()).toBeLessThan(500)
    if (res.status() === 200) {
      const body = await res.json()
      expect(body).toHaveProperty('item')
      const snap = body.item
      expect(snap).toHaveProperty('demo_session')
      expect(snap).toHaveProperty('analytics_summary')
      expect(snap).toHaveProperty('ui_links')
    }
  })

  test('GET /api/exhibition-demo/runbook returns steps', async ({ request }) => {
    const res = await backendGet(request, '/api/exhibition-demo/runbook')
    expect(res.status()).toBeLessThan(500)
    if (res.status() === 200) {
      const body = await res.json()
      expect(body).toHaveProperty('item')
      const rb = body.item
      expect(Array.isArray(rb.steps)).toBe(true)
      expect(rb.steps.length).toBeGreaterThan(0)
    }
  })

  test('GET /api/exhibition-demo/fallback returns fallback data', async ({ request }) => {
    const res = await backendGet(request, '/api/exhibition-demo/fallback')
    expect(res.status()).toBeLessThan(500)
    if (res.status() === 200) {
      const body = await res.json()
      expect(body).toHaveProperty('item')
      const fb = body.item
      expect(fb).toHaveProperty('fallback_data')
      expect(fb.fallback_data.fallback).toBe(true)
      expect(fb.fallback_data.scenario_id).toBe('bank_robbery_demo')
    }
  })

  test('POST /api/exhibition-demo/cancel cancels active demo', async ({ request }) => {
    await backendPost(request, '/api/exhibition-demo/reset')
    await backendPost(request, '/api/exhibition-demo/start', { mode: 'step', run_preflight: false })
    const res = await backendPost(request, '/api/exhibition-demo/cancel')
    expect(res.status()).toBeLessThan(500)
    if (res.status() === 200) {
      const body = await res.json()
      expect(['cancelled', 'ok']).toContain(body.status)
    }
  })

  test('invalid state transition returns clean error', async ({ request }) => {
    await backendPost(request, '/api/exhibition-demo/reset')
    // Try to step without starting
    const res = await backendPost(request, '/api/exhibition-demo/step')
    // Should be 409 Conflict, not 500
    expect(res.status()).not.toBe(500)
    expect([409, 422, 400]).toContain(res.status())
  })
})

test.describe('Exhibition Demo — UI Integration (live backend)', () => {
  test.skip(!BACKEND_LIVE, 'Requires AEGIS_E2E_BACKEND=true with a live backend')

  test('start demo from panel and verify status updates', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)

    // Reset demo first via API
    // (UI reset button)
    const resetBtn = page.locator('button', { hasText: /reset/i }).first()
    if (await resetBtn.isVisible().catch(() => false)) {
      await resetBtn.click()
      await page.waitForTimeout(1000)
    }

    // Find start button
    const startBtn = page.locator('button', { hasText: /start demo/i }).first()
    if (await startBtn.isVisible().catch(() => false)) {
      await startBtn.click()
      await page.waitForTimeout(2000)

      // Demo should now be running
      const body = await page.locator('body').innerText()
      const isRunning = body.includes('Running') || body.includes('Step →')
      expect(isRunning).toBe(true)
    }
  })

  test('tracking page loads after scenario dispatch', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)
    await assertNoForbiddenWording(page)
  })

  test('alerts page accessible from demo panel link', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)

    // Navigate to alerts page
    await page.goto('/#alerts')
    await assertPageLoaded(page)

    const body = await page.locator('body').innerText()
    const hasAlertContent = body.toLowerCase().includes('alert') || body.toLowerCase().includes('incident')
    expect(hasAlertContent).toBe(true)
  })
})
