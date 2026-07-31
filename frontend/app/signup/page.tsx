'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import Link from 'next/link'

export default function SignupPage() {
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
    if (!email.trim() || !password) return setError('ایمیل و رمز عبور را وارد کنید')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return setError('ایمیل معتبر وارد کنید')
    if (password.length < 8) return setError('رمز عبور حداقل ۸ کاراکتر باشد')
    if (password !== password2) return setError('رمزهای عبور یکسان نیستند')
    if (!captchaAnswer.trim()) return setError('پاسخ کپچا را وارد کنید')
    setBusy(true)
    setError('')
    try {
      await signup(email.trim(), password, captchaToken, captchaAnswer)
      router.push('/onboarding')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'خطا در ثبت‌نام')
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
          <div className="aurora-signup-logo w-14 h-14 rounded-xl flex items-center justify-center mx-auto mb-4" style={{background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 0 32px rgba(99,102,241,0.4), 0 0 64px rgba(99,102,241,0.15)'}}>
            <Icon name="sparkles" size={28} className="text-white" />
          </div>
          <h1 className="text-xl font-extrabold mb-1 text-gradient">ثبت‌نام در Multiai</h1>
          <p className="text-sm text-[var(--text-dim)]">دسترسی به همه مدل‌های هوش مصنوعی</p>
        </div>

        {error && (
          <div className="aurora-signup-error bg-[var(--danger-dim)] text-[var(--danger)] rounded-lg p-3 text-sm mb-4 flex items-center gap-2">
            <Icon name="close" size={14} />
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">ایمیل</label>
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
                ایمیل معتبر وارد کنید
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">رمز عبور</label>
            <input
              className={`input ${passwordTouched && !passwordValid ? 'aurora-input-error' : ''}`}
              type="password"
              placeholder="حداقل ۸ کاراکتر"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onBlur={() => setPasswordTouched(true)}
              dir="ltr"
            />
            {passwordTouched && !passwordValid && (
              <p className="text-xs text-[var(--danger)] mt-1 flex items-center gap-1">
                <Icon name="close" size={10} />
                رمز عبور حداقل ۸ کاراکتر باشد
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">تکرار رمز عبور</label>
            <input
              className={`input ${password2Touched && !password2Valid ? 'aurora-input-error' : ''}`}
              type="password"
              placeholder="رمز عبور را دوباره وارد کنید"
              value={password2}
              onChange={(e) => setPassword2(e.target.value)}
              onBlur={() => setPassword2Touched(true)}
              dir="ltr"
            />
            {password2Touched && !password2Valid && (
              <p className="text-xs text-[var(--danger)] mt-1 flex items-center gap-1">
                <Icon name="close" size={10} />
                رمزهای عبور یکسان نیستند
              </p>
            )}
            {password2Touched && password2Valid && password2.length > 0 && (
              <p className="text-xs text-[var(--positive)] mt-1 flex items-center gap-1">
                <Icon name="check" size={10} />
                مطابقت دارد
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">کپچا</label>
            {captchaImg && <img src={captchaImg} alt="captcha" className="mb-2 rounded" style={{maxWidth:200,height:60}} onClick={fetchCaptcha} />}
            <input
              className="input"
              type="text"
              placeholder="پاسخ را وارد کنید"
              value={captchaAnswer}
              onChange={(e) => setCaptchaAnswer(e.target.value)}
              dir="ltr"
            />
            <button type="button" onClick={fetchCaptcha} className="auth-inline-link mt-1">
              <Icon name="refresh" size={12} />
              تصویر جدید
            </button>
          </div>
          <button className="aurora-signup-btn btn btn-primary w-full" type="submit" disabled={busy}>
            {busy ? (
              <span className="flex items-center gap-2">
                <span className="aurora-spinner" />
                در حال ثبت‌نام...
              </span>
            ) : 'ثبت‌نام'}
          </button>
        </form>

        <p className="text-center text-sm text-[var(--text-dim)] mt-5">
          قبلاً ثبت‌نام کرده‌اید؟{' '}
          <Link href="/login" className="auth-inline-link">ورود</Link>
        </p>

        {/* Trust signals */}
        <div className="aurora-trust-signals mt-6 pt-5 border-t border-[var(--border)]">
          <div className="flex items-center justify-center gap-6 text-xs text-[var(--text-muted)]">
            <span className="flex items-center gap-1.5">
              <Icon name="security" size={14} className="text-[var(--positive)]" />
              رمزنگاری SSL
            </span>
            <span className="flex items-center gap-1.5">
              <Icon name="check" size={14} className="text-[var(--positive)]" />
              بدون نیاز به VPN
            </span>
            <span className="flex items-center gap-1.5">
              <Icon name="wallet" size={14} className="text-[var(--positive)]" />
              شارژ ریالی
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
