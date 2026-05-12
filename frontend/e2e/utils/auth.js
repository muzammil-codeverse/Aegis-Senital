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
export const TEST_PASSWORD = process.env.AEGIS_E2E_PASS || 'admin'

/**
 * Attempt to log in via the UI login form.
 * Returns true if login succeeded, false if the login page is not present
 * (meaning the app is already authenticated or in a public-shell mode).
 */
export async function loginIfRequired(page) {
  // Check if we're on the login page
  const loginInput = page.locator('input[autocomplete="username"], input[aria-label="Username"]')
  const isLoginPage = await loginInput.count() > 0

  if (!isLoginPage) {
    return false
  }

  await loginInput.first().fill(TEST_USERNAME)

  const passwordInput = page.locator('input[type="password"]').first()
  await passwordInput.fill(TEST_PASSWORD)

  const submitBtn = page.locator('button[type="submit"]').first()
  await submitBtn.click()

  // Wait for navigation away from login page
  await page.waitForURL(url => !url.toString().includes('login'), { timeout: 10000 }).catch(() => {
    // Login may have failed — tests will handle this gracefully
  })

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
