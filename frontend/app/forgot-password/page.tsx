'use client'

import { useState } from 'react'
import Link from 'next/link'
import { toast } from '@/components/ui'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return toast('ایمیل خود را وارد کنید', 'error')
    setBusy(true)
    try {
      const res = await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      })
      if (res.ok) {
        setSent(true)
        toast('لینک بازنشانی رمز عبور به ایمیل شما ارسال شد', 'success')
      } else {
        const data = await res.json()
        toast(data.detail || 'خطا در ارسال ایمیل', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="card w-full max-w-sm">
        <h1 className="text-xl font-bold text-center mb-6">بازنشانی رمز عبور</h1>
        {sent ? (
          <div className="text-center">
            <p className="text-sm text-[var(--text-dim)] mb-4">
              ایمیل بازنشانی رمز عبور به <strong dir="ltr">{email}</strong> ارسال شد. لطفاً صندوق ورودی خود را بررسی کنید.
            </p>
            <Link href="/login" className="text-[var(--accent)] hover:underline text-sm">
              بازگشت به ورود
            </Link>
          </div>
        ) : (
          <>
            <p className="text-sm text-[var(--text-dim)] mb-4 text-center">
              ایمیل خود را وارد کنید تا لینک بازنشانی رمز عبور برای شما ارسال شود.
            </p>
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
              <button className="btn btn-primary w-full" type="submit" disabled={busy}>
                {busy ? 'در حال ارسال...' : 'ارسال لینک بازنشانی'}
              </button>
            </form>
            <p className="text-center text-sm text-[var(--text-dim)] mt-4">
              <Link href="/login" className="text-[var(--accent)] hover:underline">بازگشت به ورود</Link>
            </p>
          </>
        )}
      </div>
    </div>
  )
}
