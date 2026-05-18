import { expect, test } from '@playwright/test'
import { goTo } from './utils/navigation.js'
import { loginIfRequired } from './utils/auth.js'

const FORBIDDEN = [
  /Critical network error/i,
  /Production system health endpoint temporarily unavailable/i,
  /No health data reported/i,
]

test('login and dashboard avoid backend-unavailable spam', async ({ page }) => {
  await page.goto('http://localhost:5173')
  await expect(page.getByText(/Critical network error/i)).toHaveCount(0)

  for (const pattern of FORBIDDEN) {
    await expect(page.getByText(pattern)).toHaveCount(0)
  }

  await loginIfRequired(page)

  await goTo(page, 'dashboard')
  await expect(page.getByText(/Runtime Status/i)).toBeVisible()

  const pages = ['drone-operations', 'cases', 'analytics', 'model-governance', 'map-operations']
  for (const route of pages) {
    await goTo(page, route)
    for (const pattern of FORBIDDEN) {
      await expect(page.getByText(pattern)).toHaveCount(0)
    }
  }
})
