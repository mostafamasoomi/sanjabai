import { describe, it, expect } from 'vitest'

import { errorDetail, genericError } from '../../app/admin/apiError'

/**
 * Unit tests for app/admin/apiError.ts.
 *
 * The bug: AdminPanel's `api()` threw `خطای سرور (400)` as soon as it saw a
 * non-2xx status, before any caller could read the body. Every admin endpoint
 * refuses with a Persian `detail` explaining what was actually wrong, and that
 * sentence was discarded on every single failure — the admin could only ever
 * see "the server said no".
 *
 * These tests pin both halves of the contract: the Persian detail is
 * surfaced when it exists, and anything unparseable degrades to the generic
 * message instead of leaking raw HTML (or throwing a JSON parse error *over*
 * the real HTTP failure) into the panel.
 */

function jsonResponse(body: unknown, status = 400): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('errorDetail', () => {
  // ── The whole point: FastAPI's Persian `detail` reaches the caller ──────
  it("returns FastAPI's Persian detail instead of the generic message", async () => {
    const detail = 'upstream نامعتبر، گزینه‌های معتبر: bynara، gemini-api'
    expect(await errorDetail(jsonResponse({ detail }))).toBe(detail)
  })

  it('trims surrounding whitespace on the detail', async () => {
    expect(await errorDetail(jsonResponse({ detail: '  کلید ناشناخته  ' }))).toBe('کلید ناشناخته')
  })

  // ── The OpenAI-compatible routes nest it one level deeper ──────────────
  it('reads error.message for the OpenAI-shaped refusals', async () => {
    const message = 'گفتگو موقتاً غیرفعال است'
    expect(await errorDetail(jsonResponse({ error: { message, type: 'unavailable' } }))).toBe(message)
  })

  it('prefers detail over error.message when a body carries both', async () => {
    const body = { detail: 'پیام اول', error: { message: 'پیام دوم' } }
    expect(await errorDetail(jsonResponse(body))).toBe('پیام اول')
  })

  // ── Degrading safely: never leak junk, never throw over the real error ──
  it('falls back to the generic message on a non-JSON body', async () => {
    const res = new Response('<html><body>502 Bad Gateway</body></html>', { status: 502 })
    expect(await errorDetail(res)).toBe(genericError(502))
  })

  it('falls back to the generic message on an empty body', async () => {
    expect(await errorDetail(new Response('', { status: 500 }))).toBe(genericError(500))
  })

  it('falls back to the generic message on a whitespace-only body', async () => {
    expect(await errorDetail(new Response('   \n  ', { status: 500 }))).toBe(genericError(500))
  })

  it('falls back when JSON parses to something that is not an object', async () => {
    expect(await errorDetail(new Response('"just a string"', { status: 400 }))).toBe(genericError(400))
    expect(await errorDetail(new Response('null', { status: 400 }))).toBe(genericError(400))
  })

  it('falls back when detail is present but not a usable string', async () => {
    // Pydantic request-validation errors put a *list* of objects here, whose
    // `msg` fields are English library text — deliberately not shown to an
    // admin, so this must degrade rather than leak "value is not a valid int".
    const validationBody = { detail: [{ loc: ['body', 'amount'], msg: 'value is not a valid integer' }] }
    expect(await errorDetail(jsonResponse(validationBody, 422))).toBe(genericError(422))
    expect(await errorDetail(jsonResponse({ detail: '' }))).toBe(genericError(400))
    expect(await errorDetail(jsonResponse({ detail: '   ' }))).toBe(genericError(400))
    expect(await errorDetail(jsonResponse({ detail: 12345 }))).toBe(genericError(400))
  })

  it('never throws when the body stream itself fails', async () => {
    // A response whose body errors mid-read: errorDetail must return the
    // generic message, not propagate a second failure over the first one.
    const broken = {
      status: 503,
      text: async () => {
        throw new Error('network died mid-body')
      },
    } as unknown as Response
    expect(await errorDetail(broken)).toBe(genericError(503))
  })

  it('carries the real status code into the generic message', async () => {
    expect(await errorDetail(new Response('', { status: 418 }))).toBe('خطای سرور (418)')
  })
})
