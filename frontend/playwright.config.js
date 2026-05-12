import { defineConfig, devices } from '@playwright/test'

const backendCommand = process.platform === 'win32'
  ? '.\\.venv\\Scripts\\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000'
  : './.venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 60000,
  reporter: 'html',
  outputDir: 'test-results',

  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: [
    {
      command: backendCommand,
      cwd: '..',
      url: 'http://127.0.0.1:8000/',
      reuseExistingServer: !process.env.CI,
      timeout: 180000,
      env: {
        ...process.env,
        APP_ENV: process.env.APP_ENV || 'development',
        AEGIS_BOOTSTRAP_ADMIN_PASSWORD: process.env.AEGIS_BOOTSTRAP_ADMIN_PASSWORD || 'ChangeMe123',
      },
    },
    {
      command: 'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
  ],
})
