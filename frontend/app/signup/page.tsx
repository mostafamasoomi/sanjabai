'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { BrandLockup } from '@/components/BrandLockup'
import Link from 'next/link'
import { useLang } from '@/components/LanguageToggle'
import { signupPageStrings } from './page.strings'

export default function SignupPage() {
  const lang = useLang()
  const s = signupPageStrings(lang)
  // useSearchParams() called directly in a 'use client' page with no Suspense
  // boundary, matching the only other call site (app/dashboard/page.tsx:34).
  // Next needs a boundary only for a statically prerendered page; `npm run
  // build` reports /signup as ƒ (Dynamic), so there is nothing to bail out of.
  // If this page ever becomes static, the build breaks here and says so.
  const searchParams = useSearchParams()
  const ref = searchParams.get('ref') || ''
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [captchaImg, setCaptchaImg] = useState('')
  const [captchaToken, setCaptchaToken] = useState('')
  const [captchaAnswer, setCaptchaAnswer] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [emailTouched, setEmailTouched] = useState(false)
  const [passwordTouched, setPasswordTouched] = useState(false)
  const [password2Touched, setPassword2Touched] = useState(false)
  const [captchaTouched, setCaptchaTouched] = useState(false)
  const { signup } = useAuth()
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

  const emailValid = !emailTouched || !email.trim() || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  const passwordValid = !passwordTouched || !password || password.length >= 8
  const password2Valid = !password2Touched || !password2 || password === password2

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setEmailTouched(true)
    setPasswordTouched(true)
    setPassword2Touched(true)
    if (!email.trim() || !password) return setError(s.errMissingFields)
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return setError(s.errEmailInvalid)
    if (password.length < 8) return setError(s.errPasswordTooShort)
    if (password !== password2) return setError(s.errPasswordsMismatch)
    if (!captchaAnswer.trim()) return setError(s.errCaptchaRequired)
    setBusy(true)
    setError('')
    try {
      await signup(email.trim(), password, captchaToken, captchaAnswer, ref)
      router.push('/onboarding')
    } catch (err: unknown) {
      // err.message may be a backend-sourced Persian error string (e.g.
      // "email already registered") — rendered verbatim in both languages,
      // see the handoff report.
      setError(err instanceof Error ? err.message : s.errSignupFailed)
      fetchCaptcha()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="aurora-signup-wrapper min-h-[80vh] flex items-center justify-center">
      <div className="aurora-signup-card card w-full max-w-sm">
        {/* Header */}
        <div className="text-center mb-6">
          {/* Was `.aurora-signup-logo`: a sparkles glyph in a gradient tile.
              This was the rule's only user, so it is gone from globals.css
              too. */}
          <div className="flex justify-center mb-4">
            <BrandLockup height={40} />
          </div>
          <h1 className="text-xl font-extrabold mb-1 text-gradient">{s.title}</h1>
          <p className="text-sm text-[var(--text-dim)]">{s.subtitle}</p>
        </div>

        {ref && (
          <div className="aurora-signup-referral-banner bg-[var(--accent-dim)] text-[var(--accent)] rounded-lg p-3 text-sm mb-4 flex items-center gap-2">
            <Icon name="referral" size={14} />
            {s.referralBanner}
          </div>
        )}

        {error && (
          <div className="aurora-signup-error bg-[var(--danger-dim)] text-[var(--danger)] rounded-lg p-3 text-sm mb-4 flex items-center gap-2">
            <Icon name="close" size={14} />
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">{s.emailLabel}</label>
            <input
              className={`input ${emailTouched && !emailValid ? 'aurora-input-error' : ''}`}
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => setEmailTouched(true)}
              dir="ltr"
            />
            {emailTouched && !emailValid && (
              <p className="text-xs text-[var(--danger)] mt-1 flex items-center gap-1">
                <Icon name="close" size={10} />
                {s.emailInvalid}
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">{s.passwordLabel}</label>
            <input
              className={`input ${passwordTouched && !passwordValid ? 'aurora-input-error' : ''}`}
              type="password"
              placeholder={s.passwordPlaceholder}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onBlur={() => setPasswordTouched(true)}
              dir="ltr"
            />
            {passwordTouched && !passwordValid && (
              <p className="text-xs text-[var(--danger)] mt-1 flex items-center gap-1">
                <Icon name="close" size={10} />
                {s.passwordTooShort}
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">{s.password2Label}</label>
            <input
              className={`input ${password2Touched && !password2Valid ? 'aurora-input-error' : ''}`}
              type="password"
              placeholder={s.password2Placeholder}
              value={password2}
              onChange={(e) => setPassword2(e.target.value)}
              onBlur={() => setPassword2Touched(true)}
              dir="ltr"
            />
            {password2Touched && !password2Valid && (
              <p className="text-xs text-[var(--danger)] mt-1 flex items-center gap-1">
                <Icon name="close" size={10} />
                {s.passwordsMismatch}
              </p>
            )}
            {password2Touched && password2Valid && password2.length > 0 && (
              <p className="text-xs text-[var(--positive)] mt-1 flex items-center gap-1">
                <Icon name="check" size={10} />
                {s.passwordsMatch}
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">{s.captchaLabel}</label>
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
          <button className="aurora-signup-btn btn btn-primary w-full" type="submit" disabled={busy}>
            {busy ? (
              <span className="flex items-center gap-2">
                <span className="aurora-spinner" />
                {s.submitBusy}
              </span>
            ) : s.submit}
          </button>
        </form>

        <p className="text-center text-sm text-[var(--text-dim)] mt-5">
          {s.haveAccount}{' '}
          <Link href="/login" className="auth-inline-link">{s.login}</Link>
        </p>

        {/* Trust signals */}
        <div className="aurora-trust-signals mt-6 pt-5 border-t border-[var(--border)]">
          <div className="flex items-center justify-center gap-6 text-xs text-[var(--text-muted)]">
            <span className="flex items-center gap-1.5">
              <Icon name="security" size={14} className="text-[var(--positive)]" />
              {s.trustSsl}
            </span>
            <span className="flex items-center gap-1.5">
              <Icon name="check" size={14} className="text-[var(--positive)]" />
              {s.trustNoVpn}
            </span>
            <span className="flex items-center gap-1.5">
              <Icon name="wallet" size={14} className="text-[var(--positive)]" />
              {s.trustTomanTopUp}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
