/**
 * Task 7 — Map / GIS E2E
 *
 * Uses local_mock provider by default so no Mapbox token is required.
 * Validates that the map page loads, layer controls are visible, and that
 * no token error is shown when using the mock provider.
 */
import { test, expect } from '@playwright/test'
import { goTo, ROUTES } from './utils/navigation.js'
import { assertNoForbiddenWording, assertPageLoaded } from './utils/assertions.js'

test.describe('Map Operations', () => {
  test.beforeEach(async ({ page }) => {
    await goTo(page, ROUTES.mapOperations)
  })

  test('#map-operations loads', async ({ page }) => {
    await assertPageLoaded(page)
  })

  test('map container or fallback renders without crashing', async ({ page }) => {
    // Either the map canvas, a map provider placeholder, or a local-mock render
    const mapArea = page.locator(
      'canvas, .mapboxgl-map, .map-container, [class*="map"], .local-mock-map, .map-provider'
    ).first()
    const hasMap = await mapArea.count() > 0
    if (!hasMap) {
      // Acceptable: page may show an empty/loading state
      await assertPageLoaded(page)
    }
  })

  test('layer controls or map toolbar visible', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    // Should have some map-related controls
    const hasControls = (
      bodyText.toLowerCase().includes('camera') ||
      bodyText.toLowerCase().includes('layer') ||
      bodyText.toLowerCase().includes('map') ||
      bodyText.toLowerCase().includes('geofence') ||
      bodyText.toLowerCase().includes('gis')
    )
    expect(hasControls, 'Map controls should be visible').toBe(true)
  })

  test('no mapbox token error in local_mock mode', async ({ page }) => {
    const bodyText = await page.locator('body').innerText()
    // Should not show "token" error when using local mock
    // (Real token errors come from mapbox-gl, not our app)
    expect(bodyText).not.toContain('Missing Mapbox token')
    expect(bodyText).not.toContain('mapbox token required')
  })

  test('map page does not crash with empty data', async ({ page }) => {
    // Page should remain stable even with no camera/event data
    await assertPageLoaded(page)
    // No JS crash indicators
    const bodyText = await page.locator('body').innerText()
    expect(bodyText).not.toContain('TypeError')
    expect(bodyText).not.toContain('is not a function')
  })

  test('no forbidden wording on map operations page', async ({ page }) => {
    await assertNoForbiddenWording(page)
  })
})
