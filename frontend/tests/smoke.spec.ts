import { test, expect } from '@playwright/test'
import { mockCatalog, signIn } from './helpers'

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
    // /chat is behind the auth guard, so the test needs a session.
    await signIn(page)
    await page.goto('/chat')
    // Welcome assistant message
    await expect(page.getByText('به Multiai خوش آمدید')).toBeVisible()
    // Model picker becomes visible once the (mocked) catalog resolves
    await expect(page.getByTestId('model-picker-trigger')).toBeVisible()
  })

  test('models page loads with catalog cards', async ({ page }) => {
    await page.goto('/models')
    // NOTE: "مدل‌ها" carries a ZWNJ (U+200C). Playwright normalizes runs of
    // whitespace in accessible names but ZWNJ is not whitespace, so an exact
    // string without it never matches. Match a substring instead, as
    // navigation.spec.ts already does.
    await expect(page.getByRole('heading', { name: /هوش مصنوعی/ }).first()).toBeVisible()
    // Each catalog entry renders as a card with its display name (h3 heading)
    await expect(page.getByRole('heading', { name: 'GPT-4o' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Claude Sonnet 4' })).toBeVisible()
  })

  test('dashboard requires auth', async ({ page }) => {
    // No token in storage -> the app shell must bounce us to /login rather
    // than render protected data. The redirect happens in an effect once the
    // auth state resolves, so wait for the URL instead of sampling it.
    await page.goto('/dashboard')
    await page.waitForURL(/\/login/)
    await expect(page.getByRole('heading', { name: /ورود/ })).toBeVisible()
  })
})
