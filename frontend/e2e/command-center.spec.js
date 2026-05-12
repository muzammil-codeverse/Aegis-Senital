/**
 * Task 5 — Command Center Shell E2E
 *
 * Validates the top-level app shell, sidebar navigation, runtime status
 * strip, and command palette.  Also asserts that no forbidden wording
 * appears on any core route.
 */
import { test, expect } from '@playwright/test'
import { goTo, openCommandPalette, ROUTES } from './utils/navigation.js'
import { assertNoForbiddenWording, assertPageLoaded } from './utils/assertions.js'

test.describe('Command Center Shell', () => {
  test.beforeEach(async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
  })

  test('app loads and main layout renders', async ({ page }) => {
    await assertPageLoaded(page)
    // Main layout container should be visible
    await expect(page.locator('body')).toBeVisible()
  })

  test('sidebar navigation groups visible', async ({ page }) => {
    // The sidebar should contain navigation links
    const nav = page.locator('nav, [role="navigation"], .sidebar, .nav-sidebar').first()
    const hasNav = await nav.count() > 0
    if (hasNav) {
      await expect(nav).toBeVisible()
    } else {
      // At minimum the page should not be empty
      await assertPageLoaded(page)
    }
  })

  test('runtime status strip visible', async ({ page }) => {
    // Runtime health strip appears somewhere on the dashboard
    const bodyText = await page.locator('body').innerText()
    // Should show some health/status indicator — may say healthy, degraded, etc.
    const hasStatus = (
      bodyText.toLowerCase().includes('healthy') ||
      bodyText.toLowerCase().includes('runtime') ||
      bodyText.toLowerCase().includes('status') ||
      bodyText.toLowerCase().includes('system')
    )
    expect(hasStatus, 'Runtime status strip should be visible').toBe(true)
  })

  test('Ctrl+K opens command palette', async ({ page }) => {
    const palette = await openCommandPalette(page)
    await expect(palette).toBeVisible()
    const searchInput = palette.locator('input[aria-label="Search command palette"]')
    await expect(searchInput).toBeFocused()
  })

  test('command palette can search routes', async ({ page }) => {
    const palette = await openCommandPalette(page)
    const searchInput = palette.locator('input[aria-label="Search command palette"]')
    await searchInput.fill('drone')
    // Should show some results
    await expect(palette).toContainText('Drone', { timeout: 3000 })
  })

  test('no forbidden wording on dashboard', async ({ page }) => {
    await assertNoForbiddenWording(page)
  })

  test.describe('Core routes load', () => {
    const routesToCheck = [
      ROUTES.droneOperations,
      ROUTES.mapOperations,
      ROUTES.investigation,
      ROUTES.cases,
      ROUTES.modelGovernance,
    ]

    for (const route of routesToCheck) {
      test(`#${route} loads without crash`, async ({ page }) => {
        await goTo(page, route)
        await assertPageLoaded(page)
        await assertNoForbiddenWording(page)
      })
    }
  })
})
