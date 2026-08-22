import { describe, it, expect, beforeEach, vi } from 'vitest'

import { apiFetch } from '../../lib/apiFetch'

/**
 * Unit tests for the apiFetch wrapper (lib/apiFetch.ts).
 *
 * This wrapper exists to satisfy backend/security.py's CsrfMiddleware,
 * which 403s any non-safe-method request to /auth/, /api-keys,
 * /referral/, or /v1/rag/ when a `session` cookie is present and the
 * request lacks an X-Requested-With header. These tests verify the
 * header is added on the right methods and that no other request
 * behaviour is disturbed.
 */

function mockFetchResponse() {
  return new Response(null, { status: 200 })
}

describe('apiFetch', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn(async () => mockFetchResponse())
    vi.stubGlobal('fetch', fetchMock)
  })

  // ── Non-safe methods get the CSRF header ─────────────────────────────
  describe('adds X-Requested-With on non-safe methods', () => {
    it.each(['POST', 'PUT', 'PATCH', 'DELETE'])('sets the header for %s', async (method) => {
      await apiFetch('/api/api-keys', { method })
      const [, init] = fetchMock.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get('X-Requested-With')).toBe('XMLHttpRequest')
    })

    it('is case-insensitive about the method string', async () => {
      await apiFetch('/api/api-keys', { method: 'post' })
      const [, init] = fetchMock.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get('X-Requested-With')).toBe('XMLHttpRequest')
    })
  })

  // ── Safe methods are left alone ───────────────────────────────────────
  describe('does not add the header on safe methods', () => {
    it('skips GET', async () => {
      await apiFetch('/api/wallet')
      const [, init] = fetchMock.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.has('X-Requested-With')).toBe(false)
    })

    it('skips explicit GET', async () => {
      await apiFetch('/api/wallet', { method: 'GET' })
      const [, init] = fetchMock.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.has('X-Requested-With')).toBe(false)
    })

    it('skips HEAD and OPTIONS', async () => {
      await apiFetch('/api/wallet', { method: 'HEAD' })
      await apiFetch('/api/wallet', { method: 'OPTIONS' })
      for (const call of fetchMock.mock.calls) {
        const headers = call[1].headers as Headers
        expect(headers.has('X-Requested-With')).toBe(false)
      }
    })
  })

  // ── Caller headers survive, in all three HeadersInit shapes ─────────
  describe('preserves caller-supplied headers', () => {
    it('merges a plain object', async () => {
      await apiFetch('/api/api-keys', {
        method: 'POST',
        headers: { Authorization: 'Bearer tok_abc', 'Content-Type': 'application/json' },
      })
      const [, init] = fetchMock.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get('Authorization')).toBe('Bearer tok_abc')
      expect(headers.get('Content-Type')).toBe('application/json')
      expect(headers.get('X-Requested-With')).toBe('XMLHttpRequest')
    })

    it('merges an array of pairs', async () => {
      await apiFetch('/api/api-keys', {
        method: 'DELETE',
        headers: [['Authorization', 'Bearer tok_xyz']],
      })
      const [, init] = fetchMock.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get('Authorization')).toBe('Bearer tok_xyz')
      expect(headers.get('X-Requested-With')).toBe('XMLHttpRequest')
    })

    it('merges a Headers instance without dropping its entries', async () => {
      const h = new Headers()
      h.set('Authorization', 'Bearer tok_headers')
      await apiFetch('/api/api-keys', { method: 'PUT', headers: h })
      const [, init] = fetchMock.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get('Authorization')).toBe('Bearer tok_headers')
      expect(headers.get('X-Requested-With')).toBe('XMLHttpRequest')
    })

    it('does not overwrite a caller-supplied X-Requested-With', async () => {
      await apiFetch('/api/api-keys', {
        method: 'POST',
        headers: { 'X-Requested-With': 'custom-value' },
      })
      const [, init] = fetchMock.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get('X-Requested-With')).toBe('custom-value')
    })
  })

  // ── Other init fields pass through untouched ─────────────────────────
  describe('passes through other request options', () => {
    it('forwards body, credentials, and signal unchanged', async () => {
      const controller = new AbortController()
      const body = JSON.stringify({ a: 1 })
      await apiFetch('/api/api-keys', {
        method: 'POST',
        body,
        credentials: 'include',
        signal: controller.signal,
      })
      const [url, init] = fetchMock.mock.calls[0]
      expect(url).toBe('/api/api-keys')
      expect(init.body).toBe(body)
      expect(init.credentials).toBe('include')
      expect(init.signal).toBe(controller.signal)
    })
  })
})
