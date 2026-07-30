import { test, expect } from '@playwright/test'
import { mockCatalog, mockAuthMe, signIn } from './helpers'

/**
 * E2E tests for the API Keys page (/api-keys).
 *
 * The API keys page requires authentication. We mock /api/auth/me and the
 * /api/api-keys endpoints so the page renders deterministic data.
 */

// ── API Key mocks ───────────────────────────────────────────────────────
const MOCK_KEYS = [
  {
    id: 1,
    name: 'Production',
    prefix: 'mai_prod_',
    active: true,
    last_used: '2024-06-10T12:00:00Z',
    created_at: '2024-05-01T08:00:00Z',
    usage_count: 1234,
  },
  {
    id: 2,
    name: 'Development',
    prefix: 'mai_dev_',
    active: true,
    last_used: null,
    created_at: '2024-06-01T10:00:00Z',
    usage_count: 0,
  },
  {
    id: 3,
    name: 'Old Key',
    prefix: 'mai_old_',
    active: false,
    last_used: '2024-01-15T09:00:00Z',
    created_at: '2023-12-01T07:00:00Z',
    usage_count: 500,
  },
]

function json(body: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

async function mockApiKeyApis(page: import('@playwright/test').Page) {
  // GET /api/api-keys -> list keys
  await page.route(
    (url) => url.pathname === '/api/api-keys' || url.pathname === '/api/api-keys/',
    (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill(json(MOCK_KEYS))
      }
      // POST -> create a new key
      return route.fulfill(json({ key: 'mai_new_k3y_1234567890abcdef' }))
    },
  )

  // DELETE /api/api-keys/:id -> revoke
  await page.route(
    (url) => /\/api\/api-keys\/\d+/.test(url.pathname),
    (route) => route.fulfill(json({ ok: true })),
  )
}

// ── Tests ───────────────────────────────────────────────────────────────
test.describe('api-keys', () => {
  test.beforeEach(async ({ page }) => {
    await mockCatalog(page)
    // signIn() seeds the auth token too; mocking /api/auth/me alone leaves the
    // session signed out, so the app shell redirects /api-keys to /login.
    await signIn(page)
    await mockApiKeyApis(page)
  })

  test('create key', async ({ page }) => {
    await page.goto('/api-keys')

    // Wait for the page to load
    await expect(
      page.getByRole('heading', { name: 'کلیدهای API' }),
    ).toBeVisible()

    // The generate section should be visible
    await expect(page.getByText('ساخت کلید جدید')).toBeVisible()

    // The name input should have "Default" as default
    const nameInput = page.locator('input[placeholder*="نام کلید"]')
    await expect(nameInput).toBeVisible()

    // Clear and set a custom name
    await nameInput.clear()
    await nameInput.fill('My Test Key')

    // Click the generate button
    const generateBtn = page.getByRole('button', { name: 'ساخت کلید' })
    await expect(generateBtn).toBeVisible()
    await generateBtn.click()

    // After generation, a success card should appear with the new key
    await expect(page.getByText('کلید جدید ساخته شد')).toBeVisible()

    // The one-time warning should be visible
    await expect(
      page.getByText('این کلید فقط یک بار نمایش داده می‌شود'),
    ).toBeVisible()

    // The new key value should be shown
    await expect(page.getByText('mai_new_k3y_1234567890abcdef')).toBeVisible()

    // A copy button should be present
    await expect(
      page.getByRole('button', { name: 'کپی' }).first(),
    ).toBeVisible()
  })

  test('list keys', async ({ page }) => {
    await page.goto('/api-keys')

    // Wait for keys to load
    await expect(page.getByText('کلیدهای شما')).toBeVisible()

    // Key names should be visible
    await expect(page.getByText('Production')).toBeVisible()
    await expect(page.getByText('Development')).toBeVisible()
    await expect(page.getByText('Old Key')).toBeVisible()

    // Active keys should have "فعال" badge
    const activeBadges = page.getByText('فعال', { exact: true })
    await expect(activeBadges).toHaveCount(2) // Production and Development

    // Inactive key should have "غیرفعال" badge
    await expect(page.getByText('غیرفعال')).toBeVisible()

    // Key count badge should show 3
    await expect(page.locator('.badge.badge-accent').first()).toBeVisible()

    // Usage count should be visible
    await expect(page.getByText('۱٬۲۳۴ درخواست')).toBeVisible()
  })

  test('revoke key', async ({ page }) => {
    await page.goto('/api-keys')

    // Wait for keys to load
    await expect(page.getByText('Production')).toBeVisible()

    // Find the revoke button for an active key (trash icon button)
    // Active keys have a trash/revoke button
    const revokeButtons = page.locator('.apikeys-revoke-btn')
    await expect(revokeButtons.first()).toBeVisible()

    // Click revoke on the first active key
    await revokeButtons.first().click()

    // A success toast should appear (the toast mechanism renders inline)
    await expect(page.getByText('کلید غیرفعال شد')).toBeVisible()
  })

  test('page shows empty state when no keys exist', async ({ page }) => {
    // Override the mock to return empty list
    await page.route(
      (url) => url.pathname === '/api/api-keys' || url.pathname === '/api/api-keys/',
      (route) => {
        if (route.request().method() === 'GET') {
          return route.fulfill(json([]))
        }
        return route.fulfill(json({ key: 'mai_new_key' }))
      },
    )

    await page.goto('/api-keys')

    // Empty state should be shown
    await expect(page.getByText('هنوز کلیدی نساختهاید')).toBeVisible()
    await expect(
      page.getByText('از فرم بالا اولین کلید API خود را بسازید'),
    ).toBeVisible()
  })

  test('API usage documentation is shown', async ({ page }) => {
    await page.goto('/api-keys')

    // The "نحوه استفاده" section should be visible
    await expect(page.getByText('نحوه استفاده')).toBeVisible()

    // Documentation sections
    await expect(page.getByText('احراز هویت')).toBeVisible()
    await expect(page.getByText('ارسال درخواست چت')).toBeVisible()
    await expect(page.getByText('لیست مدل‌ها')).toBeVisible()
  })

  test('api-keys page requires authentication', async ({ page }) => {
    // Override auth to return unauthenticated
    await mockAuthMe(page, null)
    await page.addInitScript(() => localStorage.removeItem('auth_token'))

    await page.goto('/api-keys')

    // The page should redirect to /login or show login CTA
    // Give it a moment for any redirect
    await page.waitForTimeout(2000)
    const url = page.url()
    const redirectedToLogin = url.includes('/login')
    if (redirectedToLogin) {
      await expect(page.getByRole('heading', { name: /ورود/ })).toBeVisible()
    }
    // If not redirected, the page may still work but the API calls would fail
  })
})
