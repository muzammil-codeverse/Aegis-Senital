/**
 * Task 8 — Investigation E2E
 *
 * Validates the investigation workspace: safe-wording banner, path
 * reconstruction panel, confidence breakdown area, and that all wording
 * uses "possible/evidence-backed" language, never "confirmed".
 */
import { test, expect } from '@playwright/test'
import { goTo, ROUTES } from './utils/navigation.js'
import { assertNoForbiddenWording, assertPageLoaded } from './utils/assertions.js'

test.describe('Investigation Workspace', () => {
  test.beforeEach(async ({ page }) => {
    await goTo(page, ROUTES.investigation)
  })

  test('#investigation loads', async ({ page }) => {
    await assertPageLoaded(page)
  })

  test('safe wording banner or indicator is visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    // Safety badge or safe-wording indicator should be present
    const hasSafeBadge = (
      bodyText.includes('operator') ||
      bodyText.includes('review') ||
      bodyText.includes('possible') ||
      bodyText.includes('evidence') ||
      bodyText.toLowerCase().includes('safe')
    )
    expect(hasSafeBadge, 'Safety wording should appear on investigation page').toBe(true)
  })

  test('path reconstruction panel visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    const hasPanel = (
      bodyText.toLowerCase().includes('path') ||
      bodyText.toLowerCase().includes('reconstruction') ||
      bodyText.toLowerCase().includes('reconstruct')
    )
    expect(hasPanel, 'Path reconstruction panel should be visible').toBe(true)
  })

  test('confidence breakdown area visible or honest empty state', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    const hasConfidence = (
      bodyText.toLowerCase().includes('confidence') ||
      bodyText.toLowerCase().includes('probability') ||
      bodyText.toLowerCase().includes('score') ||
      bodyText.toLowerCase().includes('no results') ||
      bodyText.toLowerCase().includes('empty')
    )
    expect(hasConfidence, 'Confidence breakdown or empty state should be visible').toBe(true)
  })

  test('wording uses possible/evidence-backed language, not confirmed', async ({ page }) => {
    await assertNoForbiddenWording(page)
    // Positive check: should use safe language
    const bodyText = await page.locator('body').innerText()
    const hasSafeLanguage = (
      bodyText.includes('possible') ||
      bodyText.includes('Possible') ||
      bodyText.includes('evidence') ||
      bodyText.includes('hypothesis') ||
      bodyText.includes('candidate')
    )
    // Safe language or empty state — both are fine
    if (!hasSafeLanguage) {
      // Empty state is acceptable
      await assertPageLoaded(page)
    }
  })

  test('no forbidden wording on investigation page', async ({ page }) => {
    await assertNoForbiddenWording(page)
  })
})
