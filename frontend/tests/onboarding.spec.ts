import { test, expect } from '@playwright/test'
import {
  CATALOG,
  mockCatalog,
  mockAuthMe,
  mockSignup,
  mockCaptcha,
  mockConversationsEmpty,
} from './helpers'

test.describe('onboarding', () => {
  test.beforeEach(async ({ page }) => {
    await mockCatalog(page)
    await mockCaptcha(page)
    await mockSignup(page)
    // Keep the session "logged in" if the auth context re-validates the token.
    await mockAuthMe(page, { id: 1, email: 'test@example.com' })
    await mockConversationsEmpty(page)
  })

  test('signup → onboarding → goal → chat', async ({ page }) => {
    await page.goto('/signup')

    // The form has password + confirm, so `input[type=password]` is not unique.
    await page.locator('input[type="email"]').fill('test@example.com')
    const passwords = page.locator('input[type="password"]')
    await passwords.nth(0).fill('secret123')
    await passwords.nth(1).fill('secret123')
    // Submission is blocked until the captcha answer is non-empty; the value
    // itself is validated server-side, which is mocked.
    await page.getByPlaceholder('پاسخ را وارد کنید').fill('1234')

    // signup triggers an SPA navigation to /onboarding.
    await Promise.all([
      page.waitForURL(/\/onboarding/),
      page.getByRole('button', { name: 'ثبت‌نام', exact: true }).click(),
    ])

    // 1) signup redirects to onboarding
    await expect(page).toHaveURL(/\/onboarding/)
    await expect(page.getByText('خوش آمدید')).toBeVisible()

    // 2) welcome -> goal selection
    await page.getByRole('button', { name: 'بیا شروع کنیم' }).click()
    await expect(page.getByText('قصد دارید چه کاری کنید؟')).toBeVisible()

    const goal = page.getByRole('button', { name: 'کدنویسی' })
    await goal.click()
    await expect(goal).toHaveClass(/border-\[var\(--accent\)\]/)

    // 3) continue -> recommendation (driven by the mocked catalog)
    await page.getByRole('button', { name: 'ادامه' }).click()
    await expect(page.getByText(/مدل پیشنهادی/)).toBeVisible()
    // The recommended model's name may appear in more than one node (card
    // title plus a summary line), so assert on the first match.
    await expect(
      page.getByText('GPT-4o').or(page.getByText('Claude Sonnet 4')).first(),
    ).toBeVisible()

    // 4) finish -> chat. `finish()` calls router.replace(), which is a client
    // navigation, so wait on the URL rather than a load event.
    await page.getByRole('button', { name: /شروع چت/ }).click()
    await page.waitForURL(/\/chat/)
  })
})
