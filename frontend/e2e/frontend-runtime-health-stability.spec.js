import { expect, test } from '@playwright/test'
import { goTo } from './utils/navigation.js'
import { loginIfRequired } from './utils/auth.js'

const FORBIDDEN = [
  /Critical network error/i,
  /Backend unavailable/i,
  /Production system health endpoint temporarily unavailable/i,
  /No health data reported/i,
]

test('runtime health stays scoped without degraded spam', async ({ page }) => {
  await page.goto('http://localhost:5173')

  for (const pattern of FORBIDDEN) {
    await expect(page.getByText(pattern)).toHaveCount(0)
  }

  await loginIfRequired(page)

  const routes = [
    'dashboard',
    'drone-operations',
    'drone-simulation',
    'map-operations',
    'drone-fusion',
    'cases',
    'analytics',
    'model-governance',
  ]

  for (const route of routes) {
    await goTo(page, route)
    for (const pattern of FORBIDDEN) {
      await expect(page.getByText(pattern)).toHaveCount(0)
    }
  }

  await goTo(page, 'dashboard')
  await expect(page.getByLabel('Runtime status strip')).toBeVisible()
})

