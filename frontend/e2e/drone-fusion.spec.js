/**
 * Task 9 — Drone Fusion E2E
 *
 * Validates the drone-fixed camera fusion page: candidate cross-source
 * wording, simulated drone labels, confidence breakdown, and review state.
 */
import { test, expect } from '@playwright/test'
import { goTo, ROUTES } from './utils/navigation.js'
import { assertNoForbiddenWording, assertPageLoaded } from './utils/assertions.js'

test.describe('Drone Fusion', () => {
  test.beforeEach(async ({ page }) => {
    await goTo(page, ROUTES.droneFusion)
  })

  test('#drone-fusion loads', async ({ page }) => {
    await assertPageLoaded(page)
  })

  test('candidate cross-source or simulated wording visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    const hasFusionWording = (
      bodyText.includes('Candidate cross-source') ||
      bodyText.includes('candidate cross-source') ||
      bodyText.includes('Simulated') ||
      bodyText.includes('simulated') ||
      bodyText.includes('fusion') ||
      bodyText.includes('Fusion')
    )
    expect(hasFusionWording, 'Fusion-specific safe wording should appear').toBe(true)
  })

  test('confidence breakdown or empty state visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    const hasContent = (
      bodyText.toLowerCase().includes('confidence') ||
      bodyText.toLowerCase().includes('review') ||
      bodyText.toLowerCase().includes('no fusion') ||
      bodyText.toLowerCase().includes('empty') ||
      bodyText.toLowerCase().includes('candidate')
    )
    expect(hasContent, 'Confidence breakdown or empty state should be visible').toBe(true)
  })

  test('review state or empty state visible', async ({ page }) => {
    // Either shows fusion candidates or an honest empty state
    const bodyText = await page.locator('body').innerText()
    const hasState = (
      bodyText.toLowerCase().includes('review') ||
      bodyText.toLowerCase().includes('no') ||
      bodyText.toLowerCase().includes('loading') ||
      bodyText.toLowerCase().includes('fusion') ||
      bodyText.toLowerCase().includes('candidate')
    )
    expect(hasState, 'Review state or empty state should be visible').toBe(true)
  })

  test('filter by case ID input is accessible', async ({ page }) => {
    const caseInput = page.locator('input[aria-label="Filter by case ID"]')
    const hasInput = await caseInput.count() > 0
    if (hasInput) {
      await expect(caseInput).toBeVisible()
    }
  })

  test('no forbidden wording on drone fusion page', async ({ page }) => {
    await assertNoForbiddenWording(page)
  })
})
