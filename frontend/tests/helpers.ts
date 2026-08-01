import type { Page } from '@playwright/test'

/**
 * Shared API mocks for the E2E suite.
 *
 * The frontend talks to a backend for the model catalog (/api/catalog/models)
 * and auth (/api/auth/*, /api/conversations, dashboard endpoints). We stub
 * these with page.route so tests are fast and deterministic and do not depend
 * on a running backend.
 */

export type MockUser = { id: number; email: string }

export const CATALOG = {
  data: [
    {
      id: 'gpt-4o',
      providerModelId: 'openai/gpt-4o',
      provider: 'OpenAI',
      displayName: 'GPT-4o',
      description: 'یک مدل چندمنظوره قدرتمند برای چت و نوشتار',
      modalities: { input: ['text'], output: ['text'] },
      capabilities: ['writing', 'chat', 'coding'],
      recommendedFor: ['general', 'writing'],
      contextWindow: 128000,
      pricing: {
        currency: 'IRT' as const,
        inputPerMillion: 15000,
        outputPerMillion: 45000,
        priceVersion: '1.0',
        effectiveFrom: '2024-01-01',
      },
      availability: 'available' as const,
      audience: ['consumer'],
      lastVerifiedAt: '2024-01-01',
      provenance: 'provider' as const,
    },
    {
      id: 'claude-sonnet-4',
      providerModelId: 'anthropic/claude-sonnet-4',
      provider: 'Anthropic',
      displayName: 'Claude Sonnet 4',
      description: 'مدل استنتاج و کدنویسی با کیفیت بالا',
      modalities: { input: ['text'], output: ['text'] },
      capabilities: ['code', 'coding', 'analysis'],
      recommendedFor: ['coding', 'analysis'],
      contextWindow: 200000,
      pricing: {
        currency: 'IRT' as const,
        inputPerMillion: 20000,
        outputPerMillion: 60000,
        priceVersion: '1.0',
        effectiveFrom: '2024-01-01',
      },
      availability: 'available' as const,
      audience: ['consumer', 'developer'],
      lastVerifiedAt: '2024-01-01',
      provenance: 'provider' as const,
    },
  ],
  generatedAt: '2024-01-01T00:00:00Z',
  source: 'approved-catalog' as const,
}

function json(body: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

/** Stub the model catalog with a small but realistic list. */
export async function mockCatalog(page: Page) {
  await page.route(
    (url) => url.toString().includes('/api/catalog/models'),
    (route) => route.fulfill(json(CATALOG)),
  )
}

/** Stub /api/auth/me. Pass `null` to simulate an unauthenticated session. */
export async function mockAuthMe(page: Page, user: MockUser | null) {
  await page.route(
    (url) => url.toString().includes('/api/auth/me'),
    (route) => {
      if (user) return route.fulfill(json(user))
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'unauthorized' }),
      })
    },
  )
}

/**
 * Stub /api/captcha. Both auth forms fetch a captcha on mount and refuse to
 * submit until the answer field is filled, so any test that submits one of
 * them needs this.
 */
export async function mockCaptcha(page: Page) {
  await page.route(
    (url) => url.toString().includes('/api/captcha'),
    (route) =>
      route.fulfill(
        json({
          token: 'test-captcha-token',
          // 1x1 transparent GIF — enough for the <img> to load.
          captcha:
            'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7',
        }),
      ),
  )
}

/** Stub the signup endpoint used by the onboarding flow. */
export async function mockSignup(
  page: Page,
  user: MockUser = { id: 1, email: 'test@example.com' },
) {
  await page.route(
    (url) => url.toString().includes('/api/auth/signup'),
    (route) => route.fulfill(json({ token: 'test-token', user })),
  )
}

/**
 * Put the page in a signed-in state.
 *
 * <AuthProvider> restores a session by reading `sanjhubai_auth_token` from
 * localStorage and validating it against /api/auth/me, so a test that wants an
 * authenticated page needs both halves. Without this the app shell's auth
 * guard redirects protected routes to /login — which is the correct behaviour,
 * and what these tests used to accidentally bypass because AuthProvider was
 * never mounted at all.
 *
 * Also stubs /api/conversations so the first-visit guard doesn't bounce the
 * session to /onboarding.
 */
export async function signIn(
  page: Page,
  user: MockUser = { id: 1, email: 'test@example.com' },
) {
  await page.addInitScript(() => {
    localStorage.setItem('sanjhubai_auth_token', 'test-token')
    // The onboarding guard checks this before hitting the network.
    localStorage.setItem('sanjhubai_onboarded', '1')
  })
  await mockAuthMe(page, user)
  await page.route(
    (url) => url.toString().includes('/api/conversations'),
    (route) => route.fulfill(json([{ id: 1, title: 'گفتگوی نمونه' }])),
  )
}

/** Stub the conversations endpoint (used by the first-visit onboarding guard). */
export async function mockConversationsEmpty(page: Page) {
  await page.route(
    (url) => url.toString().includes('/api/conversations'),
    (route) => route.fulfill(json([])),
  )
}
