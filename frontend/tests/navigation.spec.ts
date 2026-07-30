import { test, expect } from '@playwright/test'
import { mockCatalog, signIn } from './helpers'

test.describe('navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockCatalog(page)
  })

  test('sidebar / bottom-nav link navigates', async ({ page }) => {
    // The sidebar only renders for a signed-in user, and /chat is behind the
    // auth guard, so this needs a session.
    await signIn(page)
    await page.goto('/chat')
    // NAV labels contain a ZWNJ (e.g. "مدل‌ها"); match by substring. Anchor to
    // the start so this doesn't also match "مقایسه مدل‌ها", which would be a
    // strict-mode violation.
    const modelsLink = page.getByRole('link', { name: /^مدل/ })
    await expect(modelsLink).toBeVisible()
    // The click triggers a client-side (SPA) navigation; wrap it with
    // waitForURL so Playwright does not treat the navigated-away element
    // as an interrupted click.
    await Promise.all([
      page.waitForURL(/\/models/),
      modelsLink.click(),
    ])
    await expect(
      page.getByRole('heading', { name: /هوش مصنوعی/ }).first(),
    ).toBeVisible()
  })

  test('command palette opens with ⌘K / Ctrl+K', async ({ page }) => {
    await page.goto('/')
    // The ⌘K handler is a document listener attached on mount, so the key
    // press has to come after hydration — otherwise this races the JS chunks
    // and fails intermittently.
    await page.waitForLoadState('networkidle')
    const input = page.getByPlaceholder('جستجو در منوها...')
    await expect(async () => {
      await page.keyboard.press('Control+k')
      await expect(input).toBeVisible({ timeout: 1000 })
    }).toPass({ timeout: 15_000 })
    await expect(input).toBeFocused()
    // Typing filters the command list (interactive)
    await input.fill('چت')
    await expect(input).toHaveValue('چت')
    // Close with Escape
    await page.keyboard.press('Escape')
    await expect(input).toBeHidden()
  })
})
