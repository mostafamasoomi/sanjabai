'use client'

import { useState } from 'react'
import Link from 'next/link'
import { toast } from '@/components/ui'
import { apiFetch } from '@/lib/apiFetch'
import { useLang } from '@/components/LanguageToggle'
import { forgotPasswordPageStrings } from './page.strings'

export default function ForgotPasswordPage() {
  const lang = useLang()
  const s = forgotPasswordPageStrings(lang)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return toast(s.emailRequired, 'error')
    setBusy(true)
    try {
      const res = await apiFetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      })
      if (res.ok) {
        setSent(true)
        toast(s.sentToast, 'success')
      } else {
        const data = await res.json()
        // data.detail is a backend-sourced Persian error string, rendered
        // verbatim in both languages — see the handoff report.
        toast(data.detail || s.genericError, 'error')
      }
    } catch {
      toast(s.networkError, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="card w-full max-w-sm">
        <h1 className="text-xl font-bold text-center mb-6">{s.title}</h1>
        {sent ? (
          <div className="text-center">
            <p className="text-sm text-[var(--text-dim)] mb-4">
              {s.sentPrefix} <strong dir="ltr">{email}</strong> {s.sentSuffix}
            </p>
            <Link href="/login" className="text-[var(--accent)] hover:underline text-sm">
              {s.backToLogin}
            </Link>
          </div>
        ) : (
          <>
            <p className="text-sm text-[var(--text-dim)] mb-4 text-center">{s.intro}</p>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">{s.emailLabel}</label>
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
                {busy ? s.submitBusy : s.submit}
              </button>
            </form>
            <p className="text-center text-sm text-[var(--text-dim)] mt-4">
              <Link href="/login" className="text-[var(--accent)] hover:underline">{s.backToLogin}</Link>
            </p>
          </>
        )}
      </div>
    </div>
  )
}
