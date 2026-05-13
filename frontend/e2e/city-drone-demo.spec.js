import { test, expect } from '@playwright/test'
import { goTo, ROUTES } from './utils/navigation.js'
import { assertNoForbiddenWording, assertPageLoaded } from './utils/assertions.js'

const LIVE_DRONE = process.env.AEGIS_E2E_LIVE_DRONE === 'true'

test.describe('City Drone Demo Flow', () => {
  test('dashboard loads', async ({ page }) => {
    await goTo(page, ROUTES.dashboard)
    await assertPageLoaded(page)
    await assertNoForbiddenWording(page)
  })

  test('drone operations hub loads', async ({ page }) => {
    await goTo(page, ROUTES.droneOperations)
    await assertPageLoaded(page)
  })

  test('drone simulation page shows camera grid', async ({ page }) => {
    await goTo(page, ROUTES.droneSimulation)
    await assertPageLoaded(page)
    const bodyText = await page.locator('body').innerText()
    expect(bodyText.toLowerCase()).toContain('camera')
    await assertNoForbiddenWording(page)
  })

  test('drone mission planner shows city mission presets', async ({ page }) => {
    await goTo(page, ROUTES.droneMissionPlanner)
    await assertPageLoaded(page)
    const bodyText = await page.locator('body').innerText()
    expect(bodyText.toLowerCase()).toContain('preset')
    await assertNoForbiddenWording(page)
  })

  test('drone fusion shows mission context wording', async ({ page }) => {
    await goTo(page, ROUTES.droneFusion)
    await assertPageLoaded(page)
    const bodyText = await page.locator('body').innerText()
    const hasContext = bodyText.includes('Mission context') || bodyText.includes('mission context')
    expect(hasContext).toBe(true)
    await assertNoForbiddenWording(page)
  })

  test('map operations shows drone layer controls', async ({ page }) => {
    await goTo(page, ROUTES.mapOperations)
    await assertPageLoaded(page)
    const bodyText = await page.locator('body').innerText()
    const hasDroneLayerText = bodyText.toLowerCase().includes('active routes') || bodyText.toLowerCase().includes('handoff arrows')
    expect(hasDroneLayerText).toBe(true)
  })

  test('investigation page preserves safe wording', async ({ page }) => {
    await goTo(page, ROUTES.investigation)
    await assertPageLoaded(page)
    const bodyText = await page.locator('body').innerText()
    const hasSafeText = bodyText.toLowerCase().includes('possible movement path') || bodyText.toLowerCase().includes('evidence-backed')
    expect(hasSafeText).toBe(true)
    await assertNoForbiddenWording(page)
  })

  test.describe('Optional live checks', () => {
    test('live drone widgets can render', async ({ page }) => {
      test.skip(!LIVE_DRONE, 'Live drone mode disabled')
      await goTo(page, ROUTES.droneSimulation)
      await assertPageLoaded(page)
      const bodyText = await page.locator('body').innerText()
      expect(bodyText.toLowerCase()).toContain('runtime')
    })
  })
})
