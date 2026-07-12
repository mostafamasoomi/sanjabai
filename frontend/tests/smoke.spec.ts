import { test, expect } from '@playwright/test'
import { mockCatalog } from './helpers'

test.describe('smoke', () => {
  test.beforeEach(async ({ page }) => {
    // Catalog is fetched on most pages; stub it so renders are deterministic.
    await mockCatalog(page)
  })

  test('landing page loads', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/Multiai/)
    // The h1 hero heading contains "هوش مصنوعی" (it is split across two
    // text nodes, hence a role+regex match rather than getByText).
    await expect(
      page.getByRole('heading', { name: /هوش مصنوعی/ }),
    ).toBeVisible()
    // Hero CTA exists (conversion entry point). There are two "شروع رایگان"
    // links (hero + bottom banner); the hero one is first in DOM order.
    await expect(page.getByRole('link', { name: /شروع رایگان/ }).first()).toBeVisible()
  })

  test('chat page loads', async ({ page }) => {
    await page.goto('/chat')
    // Welcome assistant message
    await expect(page.getByText('به Multiai خوش آمدید')).toBeVisible()
    // Model picker becomes visible once the (mocked) catalog resolves
    await expect(page.locator('[data-testid="model-select"]')).toBeVisible()
  })

  test('models page loads with catalog cards', async ({ page }) => {
    await page.goto('/models')
    await expect(
      page.getByRole('heading', { name: 'مدلهای هوش مصنوعی' }),
    ).toBeVisible()
    // Each catalog entry renders as a card with its display name (h3 heading)
    await expect(page.getByRole('heading', { name: 'GPT-4o' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Claude Sonnet 4' })).toBeVisible()
  })

  test('dashboard requires auth', async ({ page }) => {
    // No token in storage -> the dashboard must NOT render protected data.
    await page.goto('/dashboard')
    // Either it redirects to /login or it shows an inline login CTA.
    const redirectedToLogin = page.url().includes('/login')
    if (redirectedToLogin) {
      await expect(page.getByRole('heading', { name: /ورود/ })).toBeVisible()
    } else {
      await expect(page.getByText('وارد شوید')).toBeVisible()
    }
  })
})
