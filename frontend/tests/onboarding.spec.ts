import { test, expect } from '@playwright/test'
import {
  CATALOG,
  mockCatalog,
  mockAuthMe,
  mockSignup,
  mockConversationsEmpty,
} from './helpers'

test.describe('onboarding', () => {
  test.beforeEach(async ({ page }) => {
    await mockCatalog(page)
    await mockSignup(page)
    // Keep the session "logged in" if the auth context re-validates the token.
    await mockAuthMe(page, { id: 1, email: 'test@example.com' })
    await mockConversationsEmpty(page)
  })

  test('signup → onboarding → goal → chat', async ({ page }) => {
    await page.goto('/signup')

    page.on('request', (r) => console.log('REQ', r.method(), r.url()))
    page.on('response', (r) => console.log('RES', r.status(), r.url()))
    page.on('console', (m) => console.log('PAGE', m.type(), m.text()))
    page.on('pageerror', (e) => console.log('PAGEERR', e.message))

    await page.locator('input[type="email"]').fill('test@example.com')
    await page.locator('input[type="password"]').fill('secret123')
    console.log('BEFORE CLICK url=', page.url())

    try {
      await Promise.all([
        page.waitForURL(/\/onboarding/, { timeout: 20000 }),
        page.getByRole('button', { name: 'ثبتنام' }).click(),
      ])
    } catch (e) {
      const html = await page.content()
      console.log('AFTER FAIL url=', page.url())
      console.log('HAS خوش آمدید:', html.includes('خوش آمدید'))
      console.log('HAS ایمل و رمز:', html.includes('ایمل و رمز'))
      console.log('HAS /api in html:', html.includes('/api/'))
      throw e
    }
    await page.locator('input[type="password"]').fill('secret123')
    // signup triggers an SPA navigation to /onboarding.
    await Promise.all([
      page.waitForURL(/\/onboarding/),
      page.getByRole('button', { name: 'ثبتنام' }).click(),
    ])

    // 1) signup redirects to onboarding
    await expect(page).toHaveURL(/\/onboarding/)
    await expect(page.getByText('خوش آمدید')).toBeVisible()

    // 2) welcome -> goal selection
    await page.getByRole('button', { name: 'بیا شروع کنیم' }).click()
    await expect(page.getByText('قصد دارید چه کاریم؟')).toBeVisible()

    const goal = page.getByRole('button', { name: 'کدنویسی' })
    await goal.click()
    await expect(goal).toHaveClass(/border-\[var\(--accent\)\]/)

    // 3) continue -> recommendation (driven by the mocked catalog)
    await page.getByRole('button', { name: 'ادامه' }).click()
    await expect(page.getByText(/مدل پیشنهادی/)).toBeVisible()
    await expect(
      page.getByText('GPT-4o').or(page.getByText('Claude Sonnet 4')),
    ).toBeVisible()

    // 4) finish -> chat (SPA navigation)
    await Promise.all([
      page.waitForURL(/\/chat/),
      page.getByRole('button', { name: 'شروع چت' }).click(),
    ])
    await expect(page).toHaveURL(/\/chat/)
  })
})
