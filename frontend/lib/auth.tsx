'use client'

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'

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
  signup: (email: string, password: string, captchaToken?: string, captchaAnswer?: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthCtx>({
  user: null, token: null, loading: true,
  login: async () => {}, signup: async () => {}, logout: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // Restore session on mount
  useEffect(() => {
    const t = localStorage.getItem('multiai_auth_token')
    if (t) {
      setToken(t)
      fetch('/api/auth/me', { headers: { Authorization: `Bearer ${t}` } })
        .then((r) => {
          if (r.ok) return r.json()
          // Only clear token on definitive auth failures (401/403).
          // Transient errors (500, 502, network) should NOT destroy a valid session.
          if (r.status === 401 || r.status === 403) {
            localStorage.removeItem('multiai_auth_token')
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

  const login = useCallback(async (email: string, password: string, captchaToken?: string, captchaAnswer?: string) => {
    const body: any = { email, password }
    if (captchaToken && captchaAnswer) { body.captcha_token = captchaToken; body.captcha_answer = captchaAnswer }
    const res = await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error((await res.json()).detail || 'login failed')
    const data = await res.json()
    localStorage.setItem('multiai_auth_token', data.token)
    setToken(data.token)
    setUser(data.user)
  }, [])

  const signup = useCallback(async (email: string, password: string, captchaToken?: string, captchaAnswer?: string) => {
    const body: any = { email, password }
    if (captchaToken && captchaAnswer) { body.captcha_token = captchaToken; body.captcha_answer = captchaAnswer }
    const res = await fetch('/api/auth/signup', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error((await res.json()).detail || 'signup failed')
    const data = await res.json()
    localStorage.setItem('multiai_auth_token', data.token)
    setToken(data.token)
    setUser(data.user)
  }, [])

  const logout = useCallback(() => {
    if (token) fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => {})
    localStorage.removeItem('multiai_auth_token')
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