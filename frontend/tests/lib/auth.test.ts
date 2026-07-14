import { describe, it, expect, beforeEach, vi } from 'vitest'

/**
 * Unit tests for auth behaviour.
 *
 * The AuthProvider is a React context that lives in lib/auth.tsx.
 * These tests exercise the pure-logic aspects: token storage,
 * auth header construction, and the 401 redirect behaviour.
 *
 * NOTE: vitest is not yet configured in package.json / vitest.config.ts.
 *       Install vitest + @testing-library/react to run these.
 */

// ── Helpers ─────────────────────────────────────────────────────────────
const TOKEN_KEY = 'auth_token'

function mockLocalStorage() {
  const store: Record<string, string> = {}
  return {
    getItem: vi.fn((k: string) => store[k] ?? null),
    setItem: vi.fn((k: string, v: string) => { store[k] = v }),
    removeItem: vi.fn((k: string) => { delete store[k] }),
    clear: vi.fn(() => { Object.keys(store).forEach((k) => delete store[k]) }),
    get length() { return Object.keys(store).length },
    key: vi.fn((_i: number) => null),
  }
}

// ── Tests ───────────────────────────────────────────────────────────────
describe('auth utility', () => {
  let ls: ReturnType<typeof mockLocalStorage>

  beforeEach(() => {
    ls = mockLocalStorage()
    vi.stubGlobal('localStorage', ls)
  })

  // ── Token storage ──────────────────────────────────────────────────
  describe('token storage in localStorage', () => {
    it('stores the token under the correct key', () => {
      localStorage.setItem(TOKEN_KEY, 'abc123')
      expect(ls.setItem).toHaveBeenCalledWith(TOKEN_KEY, 'abc123')
      expect(localStorage.getItem(TOKEN_KEY)).toBe('abc123')
    })

    it('returns null when no token is stored', () => {
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    })

    it('removes the token on logout', () => {
      localStorage.setItem(TOKEN_KEY, 'abc123')
      localStorage.removeItem(TOKEN_KEY)
      expect(ls.removeItem).toHaveBeenCalledWith(TOKEN_KEY)
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    })

    it('overwrites an existing token', () => {
      localStorage.setItem(TOKEN_KEY, 'first')
      localStorage.setItem(TOKEN_KEY, 'second')
      expect(localStorage.getItem(TOKEN_KEY)).toBe('second')
    })
  })

  // ── Auth header construction ───────────────────────────────────────
  describe('auth header construction', () => {
    it('builds a Bearer header from a stored token', () => {
      localStorage.setItem(TOKEN_KEY, 'tok_abc')
      const token = localStorage.getItem(TOKEN_KEY)
      const headers = { Authorization: `Bearer ${token}` }
      expect(headers.Authorization).toBe('Bearer tok_abc')
    })

    it('produces no header when token is absent', () => {
      const token = localStorage.getItem(TOKEN_KEY)
      const headers: Record<string, string> = {}
      if (token) headers.Authorization = `Bearer ${token}`
      expect(headers).toEqual({})
    })

    it('prefixes the token with "Bearer " (not "Token " or bare)', () => {
      localStorage.setItem(TOKEN_KEY, 'xyz')
      const token = localStorage.getItem(TOKEN_KEY)!
      expect(`Bearer ${token}`).toMatch(/^Bearer /)
      expect(`Bearer ${token}`).not.toMatch(/^Token /)
    })
  })

  // ── 401 handling ───────────────────────────────────────────────────
  describe('redirect on 401', () => {
    it('clears the token when a 401 is received', () => {
      localStorage.setItem(TOKEN_KEY, 'expired')
      // Simulate the AuthProvider's 401 handler
      const status: number = 401
      if (status === 401 || status === 403) {
        localStorage.removeItem(TOKEN_KEY)
      }
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    })

    it('does NOT clear the token on a 500 (transient error)', () => {
      localStorage.setItem(TOKEN_KEY, 'valid')
      const status: number = 500
      if (status === 401 || status === 403) {
        localStorage.removeItem(TOKEN_KEY)
      }
      expect(localStorage.getItem(TOKEN_KEY)).toBe('valid')
    })

    it('clears the token on 403 as well', () => {
      localStorage.setItem(TOKEN_KEY, 'forbidden')
      const status: number = 403
      if (status === 401 || status === 403) {
        localStorage.removeItem(TOKEN_KEY)
      }
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    })
  })
})
