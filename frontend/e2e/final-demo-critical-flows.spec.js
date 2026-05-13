import { expect, test } from '@playwright/test'
import path from 'node:path'
import { loginIfRequired } from './utils/auth.js'
import { goTo } from './utils/navigation.js'

test('drone simulation and uploaded video critical flows', async ({ page }) => {
  await page.goto('http://localhost:5173')
  await loginIfRequired(page)

  await goTo(page, 'drone-simulation')
  await expect(page.getByText(/Runtime data temporarily unavailable/i)).toHaveCount(0)
  const startButton = page.getByRole('button', { name: /start session/i }).first()
  if (await startButton.isVisible()) {
    await startButton.click()
    await page.waitForTimeout(2000)
  }
  await expect(page.getByRole('heading', { name: /Simulated telemetry readout/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: /Simulated Drone Camera Grid/i })).toBeVisible()

  await goTo(page, 'uploaded-video-analysis')
  await page.waitForTimeout(1500)
  await expect(page.getByText(/Runtime data temporarily unavailable/i)).toHaveCount(0)
  const input = page.locator('input[aria-label="Upload video file"]').first()
  const file = path.resolve('..', 'datasets', 'demo_videos', 'demo_people_walking.mp4')
  await input.setInputFiles(file)
  const uploadButton = page.locator('button:has-text("Upload selected file")').first()
  await expect(uploadButton).toBeEnabled()
  await uploadButton.click()
  await expect(page.getByText(/Session Library/i)).toBeVisible()
})
