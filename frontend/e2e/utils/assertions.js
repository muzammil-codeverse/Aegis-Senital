/**
 * E2E shared assertion helpers for the Aegis Sentinel Command Center.
 *
 * Safety invariants validated by these helpers must never be relaxed.
 */
import { expect } from '@playwright/test'

/** Wording that must NEVER appear in the UI. */
const FORBIDDEN_PHRASES = [
  'Suspect confirmed',
  'Identity confirmed',
  'Target confirmed',
  'Criminal confirmed',
  'Attacker confirmed',
  'Confirmed terrorist',
  'Confirmed threat',
  'Real drone pursuit',
  'Guilty',
]

/** Wording that should appear on key safety-sensitive pages. */
export const SAFE_PHRASES = [
  'Possible incident',
  'Possible identity match',
  'Candidate cross-source observation',
  'Simulated drone feed',
  'Simulated aerial observation',
  'Operator review required',
  'Evidence-backed hypothesis',
  'Model limitation',
  'Insufficient data',
]

/**
 * Assert that no forbidden wording is visible anywhere on the page.
 */
export async function assertNoForbiddenWording(page) {
  const bodyText = await page.locator('body').innerText()
  for (const phrase of FORBIDDEN_PHRASES) {
    expect(bodyText, `Forbidden phrase found: "${phrase}"`).not.toContain(phrase)
  }
}

/**
 * Assert that the page loaded successfully (not a blank screen or error boundary).
 */
export async function assertPageLoaded(page) {
  // Page should have some content
  await expect(page.locator('body')).not.toBeEmpty()
  // No unhandled error crash text
  const bodyText = await page.locator('body').innerText()
  expect(bodyText).not.toContain('Something went wrong')
  expect(bodyText).not.toContain('ChunkLoadError')
}

/**
 * Assert that an element is visible or an honest empty-state is shown.
 * Use when content may or may not be present (e.g., case list with no data).
 */
export async function assertContentOrEmptyState(page, contentLocator, emptyStateText) {
  const contentCount = await page.locator(contentLocator).count()
  if (contentCount === 0) {
    // Expect an honest empty state
    const bodyText = await page.locator('body').innerText()
    const hasEmptyState = emptyStateText.some(text => bodyText.includes(text))
    expect(hasEmptyState, `Expected content or empty state: ${emptyStateText.join(' | ')}`).toBe(true)
  }
}
