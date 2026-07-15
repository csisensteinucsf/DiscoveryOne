// Playwright configuration for DiscoveryOne E2E tests
// Usage:
//   APP_BASE_URL=https://localhost:10443 ADMIN_USER=admin ADMIN_PASS=changeme npx playwright test
// With stored auth, keep the storageState file updated via auth.setup.js.
import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.APP_BASE_URL || 'https://localhost:10443'

export default defineConfig({
  testDir: './specs',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ...(process.env.CI ? [['html', { outputFolder: 'playwright-report' }]] : [])],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    storageState: './tests/e2e/.auth/admin.json',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
