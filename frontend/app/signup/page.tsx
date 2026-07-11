'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'

export default function SignupPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const { signup } = useAuth()
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) return setError('ایمیل و رمز عبور را وارد کنید')
    if (password.length < 6) return setError('رمز عبور حداقل ۶ کاراکتر باشد')
    setBusy(true)
    setError('')
    try {
      await signup(email.trim(), password)
      router.push('/chat')
    } catch (err: any) {
      setError(err.message || 'خطا در ثبت‌نام')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="card w-full max-w-sm">
        <h1 className="text-xl font-bold text-center mb-2">ثبت‌نام در Multiai</h1>
        <p className="text-center text-sm text-[var(--text-dim)] mb-6">دسترسی به همه مدل‌های هوش مصنوعی</p>
        {error && (
          <div className="bg-[var(--danger-dim)] text-[var(--danger)] rounded-lg p-3 text-sm mb-4">{error}</div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">ایمیل</label>
            <input
              className="input"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              dir="ltr"
            />
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">رمز عبور</label>
            <input
              className="input"
              type="password"
              placeholder="حداقل ۶ کاراکتر"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              dir="ltr"
            />
          </div>
          <button className="btn btn-primary w-full" type="submit" disabled={busy}>
            {busy ? 'در حال ثبت‌نام...' : 'ثبت‌نام'}
          </button>
        </form>
        <p className="text-center text-sm text-[var(--text-dim)] mt-4">
          قبلاً ثبت‌نام کرده‌اید؟{' '}
          <a href="/login" className="text-[var(--accent)] hover:underline">ورود</a>
        </p>
      </div>
    </div>
  )
}