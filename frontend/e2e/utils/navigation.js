/**
 * E2E navigation helpers for the Aegis Sentinel Command Center.
 */
import { loginIfRequired } from './auth.js'

/** All known app route hashes */
export const ROUTES = {
  dashboard: 'dashboard',
  droneOperations: 'drone-operations',
  droneSimulation: 'drone-simulation',
  droneMissionPlanner: 'drone-mission-planner',
  droneFusion: 'drone-fusion',
  mapOperations: 'map-operations',
  investigation: 'investigation',
  cases: 'cases',
  modelGovernance: 'model-governance',
  uploadedVideoAnalysis: 'uploaded-video-analysis',
}

/**
 * Go to a route hash and handle auth if needed.
 */
export async function goTo(page, route) {
  await page.goto(`/#${route}`)
  const authed = await loginIfRequired(page)
  if (authed) {
    await page.goto(`/#${route}`)
  }
  // Give the SPA a moment to hydrate
  await page.waitForLoadState('domcontentloaded')
}

/**
 * Open the command palette with Ctrl+K and return the palette locator.
 */
export async function openCommandPalette(page) {
  await page.keyboard.press('Control+k')
  const palette = page.locator('[role="dialog"][aria-label="Command palette"]')
  await palette.waitFor({ state: 'visible', timeout: 5000 })
  return palette
}
