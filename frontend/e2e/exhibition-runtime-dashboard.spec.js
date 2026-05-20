import { test, expect } from '@playwright/test'

const APP_ROOT = process.env.AEGIS_E2E_APP_URL
  || (process.env.AEGIS_E2E_BACKEND === 'true' ? 'http://localhost:5173' : '/')
const API_BASE = process.env.AEGIS_API_BASE || 'http://localhost:8000'
const USERNAME = process.env.AEGIS_E2E_USER || 'admin'
const PASSWORDS = [
  process.env.AEGIS_E2E_PASS,
  'AegisLocalAdmin2026!',
  'ChangeMe123',
].filter(Boolean)

const FORBIDDEN_AUTH_TEXT = [
  'Authentication required',
  'Sign in to view',
  'session list unavailable: auth required',
  'metrics api unavailable',
  'No cameras registered',
]

function routeUrl(route = 'dashboard') {
  if (APP_ROOT === '/') return `/#${route}`
  return `${APP_ROOT.replace(/\/$/, '')}/#${route}`
}

async function login(page) {
  await page.goto(routeUrl('dashboard'))
  await page.waitForLoadState('domcontentloaded')
  const username = page.locator('input[autocomplete="username"], input[aria-label="Username"]').first()
  const shell = page.locator('nav, [role="navigation"], [aria-label="Search command palette"]').first()
  await Promise.race([
    username.waitFor({ state: 'visible', timeout: 15000 }).catch(() => null),
    shell.waitFor({ state: 'visible', timeout: 15000 }).catch(() => null),
  ])
  if (await shell.isVisible().catch(() => false)) return
  if (!(await username.isVisible().catch(() => false))) {
    throw new Error('Login form or authenticated shell did not become visible.')
  }

  const password = page.locator('input[type="password"]').first()
  const submit = page.locator('button[type="submit"]').first()
  let lastError = ''
  for (const candidate of PASSWORDS) {
    await username.fill(USERNAME)
    await password.fill(candidate)
    await submit.click()
    await page.waitForTimeout(1500)
    if (!(await username.isVisible().catch(() => false))) return
    lastError = await page.locator('.form-error').first().innerText().catch(() => '')
  }
  throw new Error(`Unable to log in as ${USERNAME}. ${lastError}`)
}

async function assertNoAuthBlockers(page) {
  const body = await page.locator('body').innerText()
  for (const phrase of FORBIDDEN_AUTH_TEXT) {
    expect(body, `Unexpected auth blocker: ${phrase}`).not.toContain(phrase)
  }
}

async function backendFetchFromBrowser(page, path, options = {}) {
  return page.evaluate(
    async ({ apiBase, path: requestPath, options: requestOptions }) => {
      const csrf = document.cookie
        .split('; ')
        .find(part => part.startsWith('aegis_csrf_token='))
        ?.split('=')
        .slice(1)
        .join('=')
      const response = await fetch(`${apiBase}${requestPath}`, {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}),
          ...(requestOptions.headers || {}),
        },
        ...requestOptions,
        body: requestOptions.body ? JSON.stringify(requestOptions.body) : undefined,
      })
      let json
      try {
        json = await response.json()
      } catch {
        json = null
      }
      return { status: response.status, json }
    },
    { apiBase: API_BASE, path, options },
  )
}

test.describe('Phase XIV exhibition runtime dashboard', () => {
  test('login, dashboard, maps, uploads, visual panel, and demo are not auth-blocked', async ({ page }) => {
    await login(page)
    await expect(page.locator('body')).not.toBeEmpty()
    await page.waitForTimeout(3000)
    await assertNoAuthBlockers(page)

    let body = await page.locator('body').innerText()
    expect(body).toMatch(/Command Dashboard|Bank Robbery Demo/i)
    expect(body).toMatch(/System Administrator|ADMIN|admin/i)
    expect(body).toMatch(/CAM-|Simulated City|Awaiting Visual Capture|visual snapshot/i)
    expect(body).toMatch(/Unified Review Queue|No pending review items|Loading review queue/i)
    expect(body).toMatch(/Visual Simulation Bridge|AirSim/i)

    await page.goto(routeUrl('map-operations'))
    await page.waitForTimeout(2500)
    await assertNoAuthBlockers(page)
    body = await page.locator('body').innerText()
    expect(body).toMatch(/Map Operations|Local simulation map|Stream status/i)

    await page.goto(routeUrl('uploaded-video-analysis'))
    await page.waitForTimeout(2500)
    await assertNoAuthBlockers(page)
    body = await page.locator('body').innerText()
    expect(body).toMatch(/Session Library|No uploaded-video sessions yet|uploaded-video/i)

    await page.goto(routeUrl('dashboard'))
    await page.waitForTimeout(1500)
    await assertNoAuthBlockers(page)

    const reset = await backendFetchFromBrowser(page, '/api/exhibition-demo/reset', { method: 'POST' })
    expect(reset.status).toBeLessThan(500)
    const start = await backendFetchFromBrowser(page, '/api/exhibition-demo/start', {
      method: 'POST',
      body: { mode: 'step', run_preflight: false },
    })
    expect(start.status).toBeLessThan(500)

    for (let i = 0; i < 4; i += 1) {
      const step = await backendFetchFromBrowser(page, '/api/exhibition-demo/step', { method: 'POST' })
      expect(step.status).toBeLessThan(500)
    }

    await page.reload()
    await page.waitForTimeout(3000)
    await assertNoAuthBlockers(page)
    body = await page.locator('body').innerText()
    expect(body).toMatch(/Alerts|Incidents|Track|DRONE|weapon|Bank Robbery Demo/i)
  })
})
