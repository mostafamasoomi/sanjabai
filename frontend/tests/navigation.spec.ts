import { test, expect } from '@playwright/test'
import { mockCatalog } from './helpers'

test.describe('navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockCatalog(page)
  })

  test('sidebar / bottom-nav link navigates', async ({ page }) => {
    await page.goto('/chat')
    // NAV labels contain a ZWNJ (e.g. "مدل‌ها"); match by substring.
    const modelsLink = page.getByRole('link', { name: /مدل/ })
    await expect(modelsLink).toBeVisible()
    // The click triggers a client-side (SPA) navigation; wrap it with
    // waitForURL so Playwright does not treat the navigated-away element
    // as an interrupted click.
    await Promise.all([
      page.waitForURL(/\/models/),
      modelsLink.click(),
    ])
    await expect(
      page.getByRole('heading', { name: 'مدلهای هوش مصنوعی' }),
    ).toBeVisible()
  })

  test('command palette opens with ⌘K / Ctrl+K', async ({ page }) => {
    await page.goto('/')
    await page.keyboard.press('Control+k')
    const input = page.getByPlaceholder('جستجو در منوها...')
    await expect(input).toBeVisible()
    await expect(input).toBeFocused()
    // Typing filters the command list (interactive)
    await input.fill('چت')
    await expect(input).toHaveValue('چت')
    // Close with Escape
    await page.keyboard.press('Escape')
    await expect(input).toBeHidden()
  })
})
