'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import Link from 'next/link'

export default function LoginPage() {
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
    } catch (err) { console.error('Failed to fetch captcha:', err) }
  }

  useEffect(() => { fetchCaptcha() }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) return setError('ایمیل و رمز عبور را وارد کنید')
    if (!captchaAnswer.trim()) return setError('پاسخ کپچا را وارد کنید')
    setBusy(true)
    setError('')
    try {
      await login(email.trim(), password, captchaToken, captchaAnswer)
      router.push('/chat')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'خطا در ورود')
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
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4"
            style={{
              background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
              boxShadow: '0 0 32px rgba(99, 102, 241, 0.4), 0 0 64px rgba(99, 102, 241, 0.15)',
            }}
          >
            <Icon name="chat" size={26} className="text-white" />
          </div>
          <h1 className="text-xl font-extrabold mb-1 text-gradient">ورود به حساب</h1>
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
          <div>
            <label className="text-xs text-[var(--text-secondary)] mb-1.5 block font-medium">کپچا</label>
            {captchaImg && <img src={captchaImg} alt="تصویر امنیتی کپچا" className="mb-2 rounded" style={{maxWidth:200,height:60}} onClick={fetchCaptcha} />}
            <input
              className="input"
              type="text"
              placeholder="پاسخ را وارد کنید"
              value={captchaAnswer}
              onChange={(e) => setCaptchaAnswer(e.target.value)}
              dir="ltr"
            />
            <button type="button" onClick={fetchCaptcha} className="text-xs text-[var(--accent)] mt-1">تصویر جدید</button>
          </div>
          <button className="btn btn-primary w-full" type="submit" disabled={busy}>
            {busy ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin" style={{ width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'var(--text-on-accent)', borderRadius: '50%', display: 'inline-block' }} />
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
          <Link href="/signup" className="text-[var(--accent)] hover:underline">ثبت‌نام</Link>
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
