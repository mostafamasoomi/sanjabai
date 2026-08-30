import { test, expect, type Page } from '@playwright/test'
import { mockCatalog, signIn } from './helpers'

/**
 * E2E tests for /compare's history + continue feature (compare-history-
 * continue design spec, 2026-08-30). Backend endpoints are mocked via
 * page.route -- see docs/superpowers/specs/2026-08-30-compare-history-
 * continue-design.md for the shapes asserted below.
 *
 * Catalog fixture (helpers.ts CATALOG) resolves to model A = GPT-4o
 * (openai/gpt-4o) and model B = Claude Sonnet 4 (anthropic/claude-sonnet-4)
 * -- ComparePage defaults to the first two catalog entries.
 */

function json(body: unknown, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(body) }
}

function compareResult(model: string, content: string) {
  return { model, content, elapsed: 1.2, input_tokens: 10, output_tokens: 20, cost: 500, error: null }
}

/** Mocks GET /api/v1/compare/sessions (list) and POST /api/v1/compare
 *  (first message, always creates session id 42) and POST .../sessions/42/
 *  continue (target-aware: only the targeted side(s) get a non-null
 *  result, mirroring the design spec's continue response contract). */
async function mockCompareCreateAndContinue(page: Page) {
  await page.route(
    (url) => url.pathname === '/api/v1/compare/sessions',
    (route) => route.fulfill(json([])),
  )
  await page.route(
    (url) => url.pathname === '/api/v1/compare',
    (route) =>
      route.fulfill(
        json({
          model_a: compareResult('openai/gpt-4o', 'پاسخ اول از مدل A'),
          model_b: compareResult('anthropic/claude-sonnet-4', 'پاسخ اول از مدل B'),
          faster: 'model_a',
          cheaper: 'model_a',
          messages: [],
          session_id: 42,
        }),
      ),
  )
  await page.route(
    (url) => url.pathname === '/api/v1/compare/sessions/42/continue',
    async (route) => {
      const body = route.request().postDataJSON() as { target: 'both' | 'a' | 'b'; content: string }
      const a = body.target === 'both' || body.target === 'a' ? compareResult('openai/gpt-4o', `ادامه برای A: ${body.content}`) : null
      const b = body.target === 'both' || body.target === 'b' ? compareResult('anthropic/claude-sonnet-4', `ادامه برای B: ${body.content}`) : null
      route.fulfill(
        json({
          model_a: a,
          model_b: b,
          faster: a && b ? 'model_a' : null,
          cheaper: a && b ? 'model_a' : null,
        }),
      )
    },
  )
}

async function gotoCompare(page: Page) {
  await mockCatalog(page)
  await signIn(page)
  await page.goto('/compare')
  // Model pickers resolve their default selection once the catalog loads.
  await expect(page.getByTestId('model-picker-trigger').first()).toContainText('GPT-4o')
}

test.describe('compare history + continue', () => {
  test('first compare, continue-both, and solo-send behave per the design spec', async ({ page }) => {
    await mockCompareCreateAndContinue(page)
    await gotoCompare(page)

    // RTL/fa-IR: the Persian page title renders (default locale, no login-
    // guard bounce for a signed-in user).
    await expect(page.getByRole('heading', { name: 'مقایسه مدل‌ها' })).toBeVisible()

    const panelA = page.locator('.compare-panel').nth(0)
    const panelB = page.locator('.compare-panel').nth(1)
    const textarea = page.locator('textarea').first()
    const sendBtn = page.locator('.compare-submit-btn')

    // ── 1. First compare (no session yet) -- POST /v1/compare, stores session_id ──
    await textarea.fill('اولین سوال')
    await sendBtn.click()
    await expect(panelA.locator('.chat-row')).toHaveCount(2) // user + assistant
    await expect(panelB.locator('.chat-row')).toHaveCount(2)
    await expect(panelA).toContainText('پاسخ اول از مدل A')
    await expect(panelB).toContainText('پاسخ اول از مدل B')
    // Composer clears after a successful send.
    await expect(textarea).toHaveValue('')

    // Per-side buttons only render once a session exists.
    const sendAOnly = page.getByRole('button', { name: 'فقط ارسال به A' })
    const sendBOnly = page.getByRole('button', { name: 'فقط ارسال به B' })
    await expect(sendAOnly).toBeVisible()
    await expect(sendBOnly).toBeVisible()

    // ── 2. Primary button now calls continue with target='both' ──────────
    await textarea.fill('سوال دوم')
    await sendBtn.click()
    await expect(panelA.locator('.chat-row')).toHaveCount(4)
    await expect(panelB.locator('.chat-row')).toHaveCount(4)
    await expect(panelA).toContainText('ادامه برای A: سوال دوم')
    await expect(panelB).toContainText('ادامه برای B: سوال دوم')

    // ── 3. Per-side button sends target='a' only -- B's thread is untouched ──
    await textarea.fill('فقط برای A')
    await sendAOnly.click()
    await expect(panelA.locator('.chat-row')).toHaveCount(6)
    await expect(panelB.locator('.chat-row')).toHaveCount(4) // unchanged
    await expect(panelA).toContainText('ادامه برای A: فقط برای A')
  })

  test('reopening a history entry restores both threads and unlocks continue mode', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/v1/compare/sessions',
      (route) =>
        route.fulfill(
          json([
            {
              id: 42,
              title: 'قیمت‌گذاری اشتراک',
              model_a_requested: 'openai/gpt-4o',
              model_b_requested: 'anthropic/claude-sonnet-4',
              created_at: '2026-08-29T10:00:00Z',
              updated_at: '2026-08-29T10:05:00Z',
            },
          ]),
        ),
    )
    await page.route(
      (url) => url.pathname === '/api/v1/compare/sessions/42',
      (route) =>
        route.fulfill(
          json({
            id: 42,
            title: 'قیمت‌گذاری اشتراک',
            model_a: 'openai/gpt-4o',
            model_b: 'anthropic/claude-sonnet-4',
            model_a_requested: 'openai/gpt-4o',
            model_b_requested: 'anthropic/claude-sonnet-4',
            created_at: '2026-08-29T10:00:00Z',
            updated_at: '2026-08-29T10:05:00Z',
            thread_a: [
              { role: 'user', content: 'قیمت پلن حرفه‌ای چقدره؟' },
              { role: 'assistant', content: 'پاسخ ذخیره‌شده A' },
            ],
            thread_b: [
              { role: 'user', content: 'قیمت پلن حرفه‌ای چقدره؟' },
              { role: 'assistant', content: 'پاسخ ذخیره‌شده B' },
            ],
          }),
        ),
    )

    await gotoCompare(page)

    // Below 768px the history sidebar lives in a drawer (closed by
    // default) instead of the always-visible desktop <aside> -- open it
    // first, same affordance as app/chat/page.tsx's mobile conversation
    // drawer.
    const isMobileViewport = (page.viewportSize()?.width ?? 1440) < 768
    if (isMobileViewport) {
      await page.getByRole('button', { name: 'نمایش تاریخچه' }).click()
    }

    // Sidebar lists the session with both model names + a relative time.
    await expect(page.getByText('قیمت‌گذاری اشتراک')).toBeVisible()
    await expect(page.getByText('openai/gpt-4o')).toBeVisible()
    await expect(page.getByText('anthropic/claude-sonnet-4')).toBeVisible()

    await page.getByText('قیمت‌گذاری اشتراک').click()

    const panelA = page.locator('.compare-panel').nth(0)
    const panelB = page.locator('.compare-panel').nth(1)
    await expect(panelA.locator('.chat-row')).toHaveCount(2)
    await expect(panelB.locator('.chat-row')).toHaveCount(2)
    await expect(panelA).toContainText('پاسخ ذخیره‌شده A')
    await expect(panelB).toContainText('پاسخ ذخیره‌شده B')

    // The composer is active from here -- per-side buttons are the signal
    // that the page is now in "existing session" mode (no POST /v1/compare
    // fires again for this session).
    await expect(page.getByRole('button', { name: 'فقط ارسال به A' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'فقط ارسال به B' })).toBeVisible()
  })
})
