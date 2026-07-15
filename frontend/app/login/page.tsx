'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
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
      <div className="card w-full max-w-sm" style={{ padding: 'var(--space-8)' }}>
        {/* Header */}
        <div className="text-center mb-6">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4"
            style={{
              background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
              boxShadow: '0 0 24px rgba(99, 102, 241, 0.3)',
            }}
          >
            <Icon name="chat" size={24} className="text-white" />
          </div>
          <h1 className="text-xl font-bold mb-1">ورود به حساب</h1>
          <p className="text-sm text-[var(--text-muted)]">به Multiai خوش آمدید</p>
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
            <label className="text-xs text-[var(--text-secondary)] mb-1.5 block font-medium">ایمیل</label>
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
            <label className="text-xs text-[var(--text-secondary)] mb-1.5 block font-medium">رمز عبور</label>
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
            {busy ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin" style={{ width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', display: 'inline-block' }} />
                در حال ورود...
              </span>
            ) : 'ورود'}
          </button>
        </form>

        <p className="text-center text-sm text-[var(--text-muted)] mt-4">
          <Link href="/forgot-password" className="text-[var(--accent)] hover:underline">رمز عبور را فراموش کردهاید؟</Link>
        </p>
        <p className="text-center text-sm text-[var(--text-muted)] mt-2">
          حساب کاربری ندارید؟{' '}
          <Link href="/signup" className="text-[var(--accent)] hover:underline">ثبتنام</Link>
        </p>

        {/* Trust signals */}
        <div className="mt-6 pt-5 border-t border-[var(--border)]">
          <div className="flex items-center justify-center gap-6 text-xs text-[var(--text-muted)]">
            <span className="flex items-center gap-1.5">
              <Icon name="security" size={14} className="text-[var(--positive)]" />
              امن
            </span>
            <span className="flex items-center gap-1.5">
              <Icon name="check" size={14} className="text-[var(--positive)]" />
              بدون VPN
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
