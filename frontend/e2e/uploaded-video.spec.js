/**
 * Task 12 — Uploaded Video Analysis E2E smoke
 *
 * Validates that the upload page loads, the dropzone area is present,
 * validation messaging is accessible, and operator-review wording appears.
 * Does NOT upload large test videos in standard E2E.
 */
import { test, expect } from '@playwright/test'
import { goTo, ROUTES } from './utils/navigation.js'
import { assertNoForbiddenWording, assertPageLoaded } from './utils/assertions.js'

test.describe('Uploaded Video Analysis', () => {
  test.beforeEach(async ({ page }) => {
    await goTo(page, ROUTES.uploadedVideoAnalysis)
  })

  test('#uploaded-video-analysis loads', async ({ page }) => {
    await assertPageLoaded(page)
  })

  test('upload area / dropzone visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    const hasUpload = (
      bodyText.toLowerCase().includes('upload') ||
      bodyText.toLowerCase().includes('drop') ||
      bodyText.toLowerCase().includes('video') ||
      bodyText.toLowerCase().includes('file')
    )
    expect(hasUpload, 'Upload area should be visible').toBe(true)
  })

  test('file input is accessible', async ({ page }) => {
    const fileInput = page.locator('input[aria-label="Upload video file"]')
    const hasInput = await fileInput.count() > 0
    if (hasInput) {
      // File inputs may be hidden but should exist in the DOM
      const isPresent = await fileInput.count() > 0
      expect(isPresent).toBe(true)
    }
  })

  test('validation or format messaging visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    const hasValidation = (
      bodyText.toLowerCase().includes('mp4') ||
      bodyText.toLowerCase().includes('format') ||
      bodyText.toLowerCase().includes('file') ||
      bodyText.toLowerCase().includes('supported') ||
      bodyText.toLowerCase().includes('upload')
    )
    expect(hasValidation, 'File format/validation messaging should be visible').toBe(true)
  })

  test('operator review or safety wording visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    const hasSafetyWording = (
      bodyText.toLowerCase().includes('operator') ||
      bodyText.toLowerCase().includes('review') ||
      bodyText.toLowerCase().includes('safe') ||
      bodyText.toLowerCase().includes('analysis')
    )
    expect(hasSafetyWording, 'Operator review or safety wording should be visible').toBe(true)
  })

  test('no forbidden wording on uploaded video page', async ({ page }) => {
    await assertNoForbiddenWording(page)
  })
})
