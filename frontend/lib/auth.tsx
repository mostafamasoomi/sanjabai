'use client'

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { apiFetch } from './apiFetch'

type User = {
  id: number; email: string; is_admin?: boolean; created_at?: string; referral_code?: string
  display_name?: string; avatar_url?: string; bio?: string
  preferences?: Record<string, any>
  timezone?: string; language?: string
}

type AuthCtx = {
  user: User | null
  token: string | null
  loading: boolean
  login: (email: string, password: string, captchaToken?: string, captchaAnswer?: string) => Promise<void>
  signup: (email: string, password: string, captchaToken?: string, captchaAnswer?: string, ref?: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthCtx>({
  user: null, token: null, loading: true,
  login: async () => {}, signup: async () => {}, logout: () => {},
})

/** Pure body-builder for `POST /api/auth/signup`, pulled out of the `signup`
 *  useCallback below so it is unit-testable without rendering AuthProvider
 *  (this repo has no React Testing Library installed -- see
 *  tests/lib/referralSignupChain.test.ts).
 *
 *  `ref` is the referral code read from `?ref=` on /signup (backend/auth.py's
 *  `AuthSignup.ref`). Deliberately silent about a blank one: an empty or
 *  whitespace-only ref is not an error, it just means "no invite", and the
 *  backend already no-ops an unmatched code rather than rejecting the
 *  signup over it -- so there is nothing for the client to validate either,
 *  only whether there is a ref worth sending at all. */
export function buildSignupBody(
  email: string, password: string, captchaToken?: string, captchaAnswer?: string, ref?: string,
): Record<string, unknown> {
  const body: Record<string, unknown> = { email, password }
  if (captchaToken && captchaAnswer) { body.captcha_token = captchaToken; body.captcha_answer = captchaAnswer }
  if (ref && ref.trim()) { body.ref = ref.trim() }
  return body
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // Restore session on mount
  useEffect(() => {
    const t = localStorage.getItem('sanjabai_auth_token')
    if (t) {
      setToken(t)
      fetch('/api/auth/me', { headers: { Authorization: `Bearer ${t}` } })
        .then((r) => {
          if (r.ok) return r.json()
          // Only clear token on definitive auth failures (401/403).
          // Transient errors (500, 502, network) should NOT destroy a valid session.
          if (r.status === 401 || r.status === 403) {
            localStorage.removeItem('sanjabai_auth_token')
            setToken(null)
          }
          return Promise.reject()
        })
        .then((u) => { if (u) setUser(u) })
        .catch(() => { /* token kept on transient errors — will retry on next mount */ })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  // Both /api/auth/login and /api/auth/signup return only
  // `{token, user: {id, email}}` (backend/auth.py) -- no `preferences`,
  // `display_name`, etc. If we stopped at `setUser(data.user)`, anything
  // that reads those fields (e.g. lib/panel.ts's consumer/developer nav
  // preference) would silently use the default until the next full page
  // reload. Fetch the full profile once right after and use that instead.
  // This is best-effort: on failure we keep the minimal {id, email} user
  // rather than throwing, since the login/signup itself already succeeded --
  // the session-restore effect below will fill in the rest on next mount.
  const hydrateFullUser = useCallback(async (tok: string, fallback: User) => {
    try {
      const r = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${tok}` } })
      if (r.ok) {
        const full = await r.json()
        setUser(full)
        return
      }
    } catch {
      /* network/parse failure — fall through to the minimal user below */
    }
    setUser(fallback)
  }, [])

  const login = useCallback(async (email: string, password: string, captchaToken?: string, captchaAnswer?: string) => {
    const body: any = { email, password }
    if (captchaToken && captchaAnswer) { body.captcha_token = captchaToken; body.captcha_answer = captchaAnswer }
    const res = await apiFetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error((await res.json()).detail || 'login failed')
    const data = await res.json()
    localStorage.setItem('sanjabai_auth_token', data.token)
    setToken(data.token)
    setUser(data.user)
    await hydrateFullUser(data.token, data.user)
  }, [hydrateFullUser])

  const signup = useCallback(async (email: string, password: string, captchaToken?: string, captchaAnswer?: string, ref?: string) => {
    const body = buildSignupBody(email, password, captchaToken, captchaAnswer, ref)
    const res = await apiFetch('/api/auth/signup', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error((await res.json()).detail || 'signup failed')
    const data = await res.json()
    localStorage.setItem('sanjabai_auth_token', data.token)
    setToken(data.token)
    setUser(data.user)
    await hydrateFullUser(data.token, data.user)
  }, [hydrateFullUser])

  const logout = useCallback(() => {
    if (token) apiFetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => {})
    localStorage.removeItem('sanjabai_auth_token')
    setToken(null)
    setUser(null)
  }, [token])

  return (
    <AuthContext.Provider value={{ user, token, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() { return useContext(AuthContext) }