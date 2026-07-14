import { test, expect } from '@playwright/test'
import { mockCatalog, mockAuthMe } from './helpers'

/**
 * E2E tests for the wallet page (/wallet).
 *
 * The wallet page requires authentication. We mock /api/auth/me so the
 * frontend considers the session valid, and mock the wallet API endpoints
 * so the page renders deterministic data.
 */

// ── Wallet API mocks ────────────────────────────────────────────────────
const MOCK_BALANCE = { balance: 1_250_000 }
const MOCK_LEDGER = [
  {
    id: 1,
    amount: 500_000,
    balance_after: 500_000,
    reason: 'شارژ حساب',
    created_at: '2024-06-01T10:00:00Z',
  },
  {
    id: 2,
    amount: -20_000,
    balance_after: 480_000,
    reason: 'استفاده از API',
    created_at: '2024-06-02T14:30:00Z',
  },
  {
    id: 3,
    amount: 770_000,
    balance_after: 1_250_000,
    reason: 'شارژ حساب',
    created_at: '2024-06-03T09:15:00Z',
  },
]
const MOCK_PAYMENTS = [
  {
    id: 101,
    amount: 500_000,
    status: 'paid',
    created_at: '2024-06-01T10:00:00Z',
  },
]
const MOCK_PACKAGES = [
  {
    id: 'starter',
    name_fa: 'بسته شروع',
    name_en: 'Starter Pack',
    base_amount: 100_000,
    bonus_percent: 10,
    total_credits: 110_000,
  },
  {
    id: 'pro',
    name_fa: 'بسته حرفه‌ای',
    name_en: 'Pro Pack',
    base_amount: 1_000_000,
    bonus_percent: 20,
    total_credits: 1_200_000,
  },
]

function json(body: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

async function mockWalletApis(page: import('@playwright/test').Page) {
  await page.route(
    (url) => {
      const p = url.pathname
      return p === '/api/wallet' || p === '/api/wallet/'
    },
    (route) => route.fulfill(json(MOCK_BALANCE)),
  )
  await page.route(
    (url) => url.pathname === '/api/wallet/ledger',
    (route) => route.fulfill(json(MOCK_LEDGER)),
  )
  await page.route(
    (url) => url.pathname === '/api/payment/history',
    (route) => route.fulfill(json(MOCK_PAYMENTS)),
  )
  await page.route(
    (url) => url.pathname === '/api/credit-packages',
    (route) => route.fulfill(json(MOCK_PACKAGES)),
  )
  await page.route(
    (url) => url.pathname === '/api/wallet/topup',
    (route) => route.fulfill(json({ balance_after: 2_250_000 })),
  )
}

// ── Tests ───────────────────────────────────────────────────────────────
test.describe('wallet', () => {
  test.beforeEach(async ({ page }) => {
    await mockCatalog(page)
    await mockAuthMe(page, { id: 1, email: 'test@example.com' })
    await mockWalletApis(page)
  })

  test('wallet page loads with balance', async ({ page }) => {
    await page.goto('/wallet')

    // The page heading (Persian: کیف پول)
    await expect(
      page.getByRole('heading', { name: 'کیف پول' }),
    ).toBeVisible()

    // Balance should be displayed (formatted as Persian numerals)
    // 1,250,000 IRR in fa-IR locale
    await expect(page.getByText('موجودی فعلی')).toBeVisible()

    // The "top up" card title (شارژ حساب)
    await expect(page.getByText('شارژ حساب')).toBeVisible()
  })

  test('topup flow UI', async ({ page }) => {
    await page.goto('/wallet')

    // Wait for loading to finish (balance card appears)
    await expect(page.getByText('موجودی فعلی')).toBeVisible()

    // Click a preset amount button (e.g. "۱۰۰ هزار")
    const presetBtn = page.getByRole('button', { name: /۱۰۰ هزار/ })
    await expect(presetBtn).toBeVisible()
    await presetBtn.click()

    // The topup button should show the amount
    const topupBtn = page.getByRole('button', { name: /شارژ/ }).last()
    await expect(topupBtn).toBeVisible()
    await expect(topupBtn).toBeEnabled()

    // Click the topup button to trigger confirmation modal
    await topupBtn.click()

    // Confirmation modal should appear with "تایید شارژ"
    await expect(page.getByText('تایید شارژ')).toBeVisible()

    // Cancel the modal
    await page.getByRole('button', { name: 'انصراف' }).click()
    await expect(page.getByText('تایید شارژ')).toBeHidden()
  })

  test('ledger table displays', async ({ page }) => {
    await page.goto('/wallet')

    // Wait for ledger section to appear
    await expect(page.getByText('تاریخچه تراکنشها')).toBeVisible()

    // Filter tabs should be present
    await expect(page.getByRole('button', { name: 'همه' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'واریز' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'برداشت' })).toBeVisible()

    // Ledger rows should be rendered (at least one reason text)
    await expect(page.getByText('شارژ حساب').first()).toBeVisible()
    await expect(page.getByText('استفاده از API')).toBeVisible()

    // Table headers
    await expect(page.getByRole('columnheader', { name: 'تاریخ' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'شرح' })).toBeVisible()
  })

  test('credit packages section displays', async ({ page }) => {
    await page.goto('/wallet')

    await expect(page.getByText('بستههای اعتباری')).toBeVisible()
    await expect(page.getByText('بسته شروع')).toBeVisible()
    await expect(page.getByText('بسته حرفه‌ای')).toBeVisible()
  })

  test('payment history section displays', async ({ page }) => {
    await page.goto('/wallet')

    await expect(page.getByText('تاریخچه پرداختها')).toBeVisible()
    // Payment status badge
    await expect(page.getByText('موفق')).toBeVisible()
  })

  test('wallet page shows login prompt when not authenticated', async ({ page }) => {
    // Override auth to return unauthenticated
    await mockAuthMe(page, null)
    // Also need to clear any stored token
    await page.addInitScript(() => localStorage.removeItem('auth_token'))

    await page.goto('/wallet')

    // Should show login prompt
    await expect(page.getByText('برای مشاهده کیف پول، ابتدا وارد حساب خود شوید.')).toBeVisible()
    await expect(page.getByRole('link', { name: 'ورود' })).toBeVisible()
  })
})
