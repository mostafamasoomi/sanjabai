'use client'

import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export default function ReferralPage() {
  const { user, loading: authLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace('/login')
    }
  }, [authLoading, user, router])

  if (authLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', padding: '1rem 0' }}>
        <div className="skeleton" style={{ width: '8rem', height: '1.5rem' }} />
        <div className="skeleton" style={{ width: '100%', height: '6rem', borderRadius: 'var(--radius-md)' }} />
        <div className="skeleton" style={{ width: '100%', height: '4rem', borderRadius: 'var(--radius-md)' }} />
      </div>
    )
  }

  if (!user) return null

  const referralLink = `${typeof window !== 'undefined' ? window.location.origin : ''}/signup?ref=${user.referral_code || ''}`

  const copyLink = () => {
    navigator.clipboard?.writeText(referralLink)
  }

  return (
    <div style={{ maxWidth: '40rem', margin: '0 auto', padding: '1rem 0' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <div
          style={{
            width: '2.5rem',
            height: '2.5rem',
            borderRadius: 'var(--radius-md)',
            background: 'var(--accent-dim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name="referral" size={20} className="text-accent" />
        </div>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>دعوت از دوستان</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>دوستان خود را دعوت کنید و پاداش بگیرید</p>
        </div>
      </div>

      {/* Referral Code Card */}
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div style={{ marginBottom: '1rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 500 }}>کد دعوت شما</span>
        </div>
        <div className="flex gap-2 items-center">
          <code
            style={{
              flex: 1,
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-elevated)',
              fontSize: '0.875rem',
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-primary)',
              direction: 'ltr',
              textAlign: 'center',
              letterSpacing: '0.1em',
            }}
          >
            {user.referral_code || 'در حال بارگذاری...'}
          </code>
          <button className="btn btn-primary btn-sm" onClick={copyLink} style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
            <Icon name="copy" size={14} />
            کپی
          </button>
        </div>
      </div>

      {/* How it works */}
      <div className="card">
        <h2 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1rem' }}>نحوه کار</h2>
        <div className="flex flex-col gap-3">
          {[
            { step: '۱', text: 'لینک دعوت خود را با دوستان به اشتراک بگذارید' },
            { step: '۲', text: 'دوست شما ثبت‌نام و اولین شارژ را انجام می‌دهد' },
            { step: '۳', text: 'هر دوی شما پاداش اعتباری دریافت می‌کنید' },
          ].map((item) => (
            <div key={item.step} className="flex items-center gap-3">
              <div
                style={{
                  width: '2rem',
                  height: '2rem',
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--accent-dim)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.875rem',
                  fontWeight: 700,
                  color: 'var(--accent)',
                  flexShrink: 0,
                }}
              >
                {item.step}
              </div>
              <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>{item.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
