import { test, expect } from '@playwright/test'

test.describe('Smoke', () => {
  test('landing and nav', async ({ page }) => {
    await page.goto('/cases')
    await expect(page.getByRole('link', { name: 'Cases' })).toBeVisible()
    await expect(page.locator('header, .page-header, h1')).not.toHaveCount(0)
  })

  test('open System users table', async ({ page }) => {
    await page.goto('/system')
    await expect(page.getByText('Users')).toBeVisible()
    await expect(page.getByRole('table')).toBeVisible()
  })
})
