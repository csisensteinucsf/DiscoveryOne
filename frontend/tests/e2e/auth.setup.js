// Bootstrap an authenticated storage state for admin-driven tests.
// Run before tests: `node tests/e2e/auth.setup.js`
import { chromium } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const baseURL = process.env.APP_BASE_URL || 'https://localhost:10443'
const username = process.env.ADMIN_USER || 'admin'
const password = process.env.ADMIN_PASS || 'changeme'
const storagePath = path.resolve('./tests/e2e/.auth/admin.json')

async function main() {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage()
  await page.goto(baseURL)
  await page.fill('input[placeholder="Email or Username"]', username)
  await page.fill('input[type="password"]', password)
  await page.click('button:has-text("Login")')
  await page.waitForURL('**/cases', { timeout: 15000 })

  fs.mkdirSync(path.dirname(storagePath), { recursive: true })
  await page.context().storageState({ path: storagePath })
  await browser.close()
  console.log(`Stored admin session at ${storagePath}`)
}

main().catch((err) => {
  console.error('Auth bootstrap failed:', err)
  process.exit(1)
})
