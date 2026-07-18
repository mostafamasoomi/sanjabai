# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: onboarding.spec.ts >> onboarding >> signup → onboarding → goal → chat
- Location: tests/onboarding.spec.ts:19:7

# Error details

```
TimeoutError: page.waitForURL: Timeout 20000ms exceeded.
=========================== logs ===========================
waiting for navigation until "load"
============================================================
```

# Page snapshot

```yaml
- generic [ref=e1]:
  - generic [ref=e2]:
    - complementary [ref=e3]:
      - generic [ref=e4]:
        - generic [ref=e6]: M
        - link "Multiai" [ref=e7] [cursor=pointer]:
          - /url: /
      - navigation [ref=e9]:
        - generic [ref=e10]:
          - generic [ref=e11]: اصلی
          - link "چت" [ref=e12] [cursor=pointer]:
            - /url: /chat
            - img [ref=e13]
            - generic [ref=e15]: چت
          - link "مدل‌ها" [ref=e16] [cursor=pointer]:
            - /url: /models
            - img [ref=e17]
            - generic [ref=e19]: مدل‌ها
          - link "مقایسه" [ref=e20] [cursor=pointer]:
            - /url: /compare
            - img [ref=e21]
            - generic [ref=e23]: مقایسه
          - link "Playground" [ref=e24] [cursor=pointer]:
            - /url: /playground
            - img [ref=e25]
            - generic [ref=e27]: Playground
        - generic [ref=e28]:
          - generic [ref=e29]: ابزارها
          - link "داشبورد" [ref=e30] [cursor=pointer]:
            - /url: /dashboard
            - img [ref=e31]
            - generic [ref=e33]: داشبورد
          - link "کیف پول" [ref=e34] [cursor=pointer]:
            - /url: /wallet
            - img [ref=e35]
            - generic [ref=e37]: کیف پول
          - link "تعرفه‌ها" [ref=e38] [cursor=pointer]:
            - /url: /pricing
            - img [ref=e39]
            - generic [ref=e41]: تعرفه‌ها
          - link "کلید API" [ref=e42] [cursor=pointer]:
            - /url: /api-keys
            - img [ref=e43]
            - generic [ref=e45]: کلید API
        - generic [ref=e46]:
          - generic [ref=e47]: حساب
          - link "پروفایل" [ref=e48] [cursor=pointer]:
            - /url: /profile
            - img [ref=e49]
            - generic [ref=e51]: پروفایل
          - link "دعوت" [ref=e52] [cursor=pointer]:
            - /url: /referral
            - img [ref=e53]
            - generic [ref=e55]: دعوت
          - link "مدیریت" [ref=e56] [cursor=pointer]:
            - /url: /admin
            - img [ref=e57]
            - generic [ref=e59]: مدیریت
      - link "ورود / ثبت‌نام" [ref=e61] [cursor=pointer]:
        - /url: /login
    - generic [ref=e62]:
      - banner [ref=e63]:
        - generic [ref=e64]:
          - button "جستجو ⌘K" [ref=e65] [cursor=pointer]:
            - img [ref=e66]
            - generic [ref=e68]: جستجو
            - generic [ref=e69]: ⌘K
          - button "حالت روشن" [ref=e70] [cursor=pointer]: ☀️
          - link "ورود" [ref=e71] [cursor=pointer]:
            - /url: /login
      - main [ref=e72]:
        - generic [ref=e74]:
          - heading "ثبت‌نام در Multiai" [level=1] [ref=e75]
          - paragraph [ref=e76]: دسترسی به همه مدل‌های هوش مصنوعی
          - generic [ref=e77]:
            - generic [ref=e78]:
              - generic [ref=e79]: ایمیل
              - textbox "you@example.com" [ref=e80]: test@example.com
            - generic [ref=e81]:
              - generic [ref=e82]: رمز عبور
              - textbox "حداقل ۶ کاراکتر" [active] [ref=e83]: secret123
            - button "ثبت‌نام" [ref=e84] [cursor=pointer]
          - paragraph [ref=e85]:
            - text: قبلاً ثبت‌نام کرده‌اید؟
            - link "ورود" [ref=e86] [cursor=pointer]:
              - /url: /login
  - alert [ref=e87]
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test'
  2  | import {
  3  |   CATALOG,
  4  |   mockCatalog,
  5  |   mockAuthMe,
  6  |   mockSignup,
  7  |   mockConversationsEmpty,
  8  | } from './helpers'
  9  | 
  10 | test.describe('onboarding', () => {
  11 |   test.beforeEach(async ({ page }) => {
  12 |     await mockCatalog(page)
  13 |     await mockSignup(page)
  14 |     // Keep the session "logged in" if the auth context re-validates the token.
  15 |     await mockAuthMe(page, { id: 1, email: 'test@example.com' })
  16 |     await mockConversationsEmpty(page)
  17 |   })
  18 | 
  19 |   test('signup → onboarding → goal → chat', async ({ page }) => {
  20 |     await page.goto('/signup')
  21 | 
  22 |     page.on('request', (r) => console.log('REQ', r.method(), r.url()))
  23 |     page.on('response', (r) => console.log('RES', r.status(), r.url()))
  24 |     page.on('console', (m) => console.log('PAGE', m.type(), m.text()))
  25 |     page.on('pageerror', (e) => console.log('PAGEERR', e.message))
  26 | 
  27 |     await page.locator('input[type="email"]').fill('test@example.com')
  28 |     await page.locator('input[type="password"]').fill('secret123')
  29 |     console.log('BEFORE CLICK url=', page.url())
  30 | 
  31 |     try {
  32 |       await Promise.all([
> 33 |         page.waitForURL(/\/onboarding/, { timeout: 20000 }),
     |              ^ TimeoutError: page.waitForURL: Timeout 20000ms exceeded.
  34 |         page.getByRole('button', { name: 'ثبت‌نام' }).click(),
  35 |       ])
  36 |     } catch (e) {
  37 |       const html = await page.content()
  38 |       console.log('AFTER FAIL url=', page.url())
  39 |       console.log('HAS خوش آمدید:', html.includes('خوش آمدید'))
  40 |       console.log('HAS ایمل و رمز:', html.includes('ایمل و رمز'))
  41 |       console.log('HAS /api in html:', html.includes('/api/'))
  42 |       throw e
  43 |     }
  44 |     await page.locator('input[type="password"]').fill('secret123')
  45 |     // signup triggers an SPA navigation to /onboarding.
  46 |     await Promise.all([
  47 |       page.waitForURL(/\/onboarding/),
  48 |       page.getByRole('button', { name: 'ثبت‌نام' }).click(),
  49 |     ])
  50 | 
  51 |     // 1) signup redirects to onboarding
  52 |     await expect(page).toHaveURL(/\/onboarding/)
  53 |     await expect(page.getByText('خوش آمدید')).toBeVisible()
  54 | 
  55 |     // 2) welcome -> goal selection
  56 |     await page.getByRole('button', { name: 'بیا شروع کنیم' }).click()
  57 |     await expect(page.getByText('قصد دارید چه کاریم؟')).toBeVisible()
  58 | 
  59 |     const goal = page.getByRole('button', { name: 'کدنویسی' })
  60 |     await goal.click()
  61 |     await expect(goal).toHaveClass(/border-\[var\(--accent\)\]/)
  62 | 
  63 |     // 3) continue -> recommendation (driven by the mocked catalog)
  64 |     await page.getByRole('button', { name: 'ادامه' }).click()
  65 |     await expect(page.getByText(/مدل پیشنهادی/)).toBeVisible()
  66 |     await expect(
  67 |       page.getByText('GPT-4o').or(page.getByText('Claude Sonnet 4')),
  68 |     ).toBeVisible()
  69 | 
  70 |     // 4) finish -> chat (SPA navigation)
  71 |     await Promise.all([
  72 |       page.waitForURL(/\/chat/),
  73 |       page.getByRole('button', { name: 'شروع چت' }).click(),
  74 |     ])
  75 |     await expect(page).toHaveURL(/\/chat/)
  76 |   })
  77 | })
  78 | 
```