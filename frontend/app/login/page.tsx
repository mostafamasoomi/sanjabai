'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import Link from 'next/link'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const { login } = useAuth()
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) return setError('ایمیل و رمز عبور را وارد کنید')
    setBusy(true)
    setError('')
    try {
      await login(email.trim(), password)
      router.push('/chat')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'خطا در ورود')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="card w-full max-w-sm">
        <h1 className="text-xl font-bold text-center mb-6">ورود به حساب</h1>
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
              placeholder="حداقل ۸ کاراکتر"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              dir="ltr"
            />
          </div>
          <button className="btn btn-primary w-full" type="submit" disabled={busy}>
            {busy ? 'در حال ورود...' : 'ورود'}
          </button>
        </form>
        <p className="text-center text-sm text-[var(--text-dim)] mt-4">
          <Link href="/forgot-password" className="text-[var(--accent)] hover:underline">رمز عبور را فراموش کردهاید؟</Link>
        </p>
        <p className="text-center text-sm text-[var(--text-dim)] mt-2">
          حساب کاربری ندارید؟{' '}
          <Link href="/signup" className="text-[var(--accent)] hover:underline">ثبتنام</Link>
        </p>
      </div>
    </div>
  )
}
