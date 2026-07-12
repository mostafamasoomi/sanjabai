'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'

export default function SignupPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [emailTouched, setEmailTouched] = useState(false)
  const [passwordTouched, setPasswordTouched] = useState(false)
  const { signup } = useAuth()
  const router = useRouter()

  const emailValid = !emailTouched || !email.trim() || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  const passwordValid = !passwordTouched || !password || password.length >= 6

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setEmailTouched(true)
    setPasswordTouched(true)
    if (!email.trim() || !password) return setError('ایمیل و رمز عبور را وارد کنید')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return setError('ایمیل معتبر وارد کنید')
    if (password.length < 6) return setError('رمز عبور حداقل ۶ کاراکتر باشد')
    setBusy(true)
    setError('')
    try {
      await signup(email.trim(), password)
      router.push('/onboarding')
    } catch (err: any) {
      setError(err.message || 'خطا در ثبتنام')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="aurora-signup-wrapper min-h-[80vh] flex items-center justify-center">
      <div className="aurora-signup-card card w-full max-w-sm">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="aurora-signup-logo w-12 h-12 rounded-xl bg-[var(--accent-dim)] flex items-center justify-center mx-auto mb-4">
            <Icon name="sparkles" size={24} className="text-[var(--accent)]" />
          </div>
          <h1 className="text-xl font-bold mb-1">ثبتنام در Multiai</h1>
          <p className="text-sm text-[var(--text-dim)]">دسترسی به همه مدلهای هوش مصنوعی</p>
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
              placeholder="حداقل ۶ کاراکتر"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onBlur={() => setPasswordTouched(true)}
              dir="ltr"
            />
            {passwordTouched && !passwordValid && (
              <p className="text-xs text-[var(--danger)] mt-1 flex items-center gap-1">
                <Icon name="close" size={10} />
                رمز عبور حداقل ۶ کاراکتر باشد
              </p>
            )}
            {passwordTouched && passwordValid && password.length >= 6 && (
              <p className="text-xs text-[var(--positive)] mt-1 flex items-center gap-1">
                <Icon name="check" size={10} />
                رمز عبور مناسب است
              </p>
            )}
          </div>
          <button className="aurora-signup-btn btn btn-primary w-full" type="submit" disabled={busy}>
            {busy ? (
              <span className="flex items-center gap-2">
                <span className="aurora-spinner" />
                در حال ثبتنام...
              </span>
            ) : 'ثبتنام'}
          </button>
        </form>

        <p className="text-center text-sm text-[var(--text-dim)] mt-5">
          قبلاً ثبتنام کردهاید؟{' '}
          <a href="/login" className="text-[var(--accent)] hover:underline">ورود</a>
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
