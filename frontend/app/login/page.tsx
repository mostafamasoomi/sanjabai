'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { BrandLockup } from '@/components/BrandLockup'
import Link from 'next/link'
import { useLang } from '@/components/LanguageToggle'
import { loginPageStrings } from './page.strings'

export default function LoginPage() {
  const lang = useLang()
  const s = loginPageStrings(lang)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [captchaImg, setCaptchaImg] = useState('')
  const [captchaToken, setCaptchaToken] = useState('')
  const [captchaAnswer, setCaptchaAnswer] = useState('')
  const { login } = useAuth()
  const router = useRouter()

  const fetchCaptcha = async () => {
    try {
      const r = await fetch('/api/captcha')
      const d = await r.json()
      setCaptchaImg(d.captcha)
      setCaptchaToken(d.token)
    } catch {}
  }

  useEffect(() => { fetchCaptcha() }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) return setError(s.errMissingFields)
    if (!captchaAnswer.trim()) return setError(s.errCaptchaRequired)
    setBusy(true)
    setError('')
    try {
      await login(email.trim(), password, captchaToken, captchaAnswer)
      router.push('/chat')
    } catch (err: unknown) {
      // err.message may be a backend-sourced Persian error string (e.g.
      // "invalid credentials") — rendered verbatim in both languages, see
      // the handoff report.
      setError(err instanceof Error ? err.message : s.errLoginFailed)
      fetchCaptcha()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="card w-full max-w-sm" style={{ padding: 'var(--space-8)' }}>
        {/* Header */}
        <div className="text-center mb-6">
          {/* The front door gets the real mark, not a chat glyph in a
              gradient tile. */}
          <div className="flex justify-center mb-4">
            <BrandLockup height={40} />
          </div>
          <h1 className="text-xl font-extrabold mb-1 text-gradient">{s.title}</h1>
          <p className="text-sm text-[var(--text-muted)]">{s.subtitle}</p>
        </div>

        {error && (
          <div
            className="rounded-lg p-3 text-sm mb-4 flex items-center gap-2"
            style={{
              background: 'rgba(248, 113, 113, 0.08)',
              border: '1px solid rgba(248, 113, 113, 0.2)',
              color: 'var(--danger)',
            }}
          >
            <Icon name="close" size={14} />
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-[var(--text-secondary)] mb-1.5 block font-medium">{s.emailLabel}</label>
            <input
              className="input"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              dir="ltr"
              autoFocus
            />
          </div>
          <div>
            <label className="text-xs text-[var(--text-secondary)] mb-1.5 block font-medium">{s.passwordLabel}</label>
            <input
              className="input"
              type="password"
              placeholder={s.passwordPlaceholder}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              dir="ltr"
            />
          </div>
          <div>
            <label className="text-xs text-[var(--text-secondary)] mb-1.5 block font-medium">{s.captchaLabel}</label>
            {captchaImg && <img src={captchaImg} alt="captcha" className="mb-2 rounded" style={{maxWidth:200,height:60}} onClick={fetchCaptcha} />}
            <input
              className="input"
              type="text"
              placeholder={s.captchaPlaceholder}
              value={captchaAnswer}
              onChange={(e) => setCaptchaAnswer(e.target.value)}
              dir="ltr"
            />
            <button type="button" onClick={fetchCaptcha} className="auth-inline-link mt-1">
              <Icon name="refresh" size={12} />
              {s.captchaRefresh}
            </button>
          </div>
          <button className="btn btn-primary w-full" type="submit" disabled={busy}>
            {busy ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin" style={{ width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'var(--text-on-accent)', borderRadius: '50%', display: 'inline-block' }} />
                {s.submitBusy}
              </span>
            ) : s.submit}
          </button>
        </form>

        <p className="text-center text-sm text-[var(--text-muted)] mt-4">
          <Link href="/forgot-password" className="auth-inline-link">{s.forgotPassword}</Link>
        </p>
        <p className="text-center text-sm text-[var(--text-muted)] mt-2">
          {s.noAccount}{' '}
          <Link href="/signup" className="auth-inline-link">{s.signup}</Link>
        </p>

        {/* Trust signals */}
        <div className="mt-6 pt-5 border-t border-[var(--border)]">
          <div className="flex items-center justify-center gap-6 text-xs text-[var(--text-muted)]">
            <span className="flex items-center gap-1.5">
              <Icon name="security" size={14} className="text-[var(--positive)]" />
              {s.trustSecure}
            </span>
            <span className="flex items-center gap-1.5">
              <Icon name="check" size={14} className="text-[var(--positive)]" />
              {s.trustNoVpn}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
