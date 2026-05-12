/**
 * E2E auth helpers.
 *
 * Strategy: The dev server starts with a login page. In E2E test mode
 * (VITE_E2E_TEST_MODE=true) a test credential is pre-seeded in dev.
 * Otherwise tests attempt login with the default dev credentials, or
 * skip gracefully if the app requires real auth.
 *
 * This helper NEVER bypasses production auth — it exercises the real
 * login flow.  Any test-mode shortcut is gated behind VITE_E2E_TEST_MODE
 * which must not be set in production builds.
 */

/** Default dev credentials. Change via env if needed. */
export const TEST_USERNAME = process.env.AEGIS_E2E_USER || 'admin'
export const TEST_PASSWORD = process.env.AEGIS_E2E_PASS || 'ChangeMe123'
const AUTH_BOOTSTRAP_TIMEOUT_MS = 45000

export async function waitForAuthBootstrap(page, timeout = AUTH_BOOTSTRAP_TIMEOUT_MS) {
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText?.toLowerCase() || ''
      return !text.includes('loading session')
    },
    null,
    { timeout },
  ).catch(() => null)
}

/**
 * Attempt to log in via the UI login form.
 * Returns true if login succeeded, false if the login page is not present
 * (meaning the app is already authenticated or in a public-shell mode).
 */
export async function loginIfRequired(page) {
  await waitForAuthBootstrap(page)

  // Check if we're on the login page
  const loginInput = page.locator('input[autocomplete="username"], input[aria-label="Username"]').first()
  const appShell = page.locator('nav, [role="navigation"], [aria-label="Search command palette"]').first()
  const isLoginPage = await loginInput.isVisible().catch(() => false)

  if (!isLoginPage) {
    return false
  }

  await loginInput.fill(TEST_USERNAME)

  const passwordInput = page.locator('input[type="password"]').first()
  await passwordInput.fill(TEST_PASSWORD)

  const submitBtn = page.locator('button[type="submit"]').first()
  await submitBtn.click()

  await waitForAuthBootstrap(page)
  await Promise.race([
    loginInput.waitFor({ state: 'hidden', timeout: AUTH_BOOTSTRAP_TIMEOUT_MS }).catch(() => null),
    appShell.waitFor({ state: 'visible', timeout: AUTH_BOOTSTRAP_TIMEOUT_MS }).catch(() => null),
  ])

  const shellVisible = await appShell.isVisible().catch(() => false)
  if (!shellVisible) {
    const loginError = await page.locator('.form-error').first().innerText().catch(() => '')
    throw new Error(`E2E login did not complete. ${loginError || 'Login form remained visible.'}`)
  }

  return true
}

/**
 * Navigate to a page and ensure we are authenticated.
 */
export async function navigateAuthenticated(page, hash) {
  await page.goto(`/#${hash}`)
  await loginIfRequired(page)
  if (page.url().includes('login')) {
    // Still on login page — re-navigate after login
    await page.goto(`/#${hash}`)
  }
}
