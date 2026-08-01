'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { Spinner, EmptyState, toast } from '@/components/ui'
import { faPrice, faNum } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════
   Hermes server catalog — landing page.

   Prices are server-authoritative: every offering comes straight from
   GET /api/hermes/offerings already converted to Toman. The frontend
   never computes or stores a currency conversion of its own.
   ═══════════════════════════════════════════════════════════════ */

type Offering = {
  id: string
  name_fa: string
  name_en: string
  description_fa: string
  arch: string
  vcpu: number
  ram_mb: number
  disk_gb: number
  traffic_tb: number
  max_skills: number
  included_credit: number
  setup_price_irt: number
  monthly_price_irt: number
  currency: string
}

export default function HermesLandingPage() {
  const { user } = useAuth()
  const [offerings, setOfferings] = useState<Offering[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/hermes/offerings')
        if (!res.ok) throw new Error('failed')
        const data = await res.json()
        if (!cancelled) setOfferings(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) toast('خطا در دریافت پلن‌های سرور هرمس', 'error')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  return (
    <div className="flex flex-col gap-6">
      {/* ── Header ── */}
      <div className="flex items-start gap-3">
        <div
          style={{
            width: '2.5rem', height: '2.5rem', borderRadius: 'var(--radius-md)',
            background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <Icon name="rocket" size={20} className="text-[var(--accent)]" />
        </div>
        <div>
          <h1 className="page-title">سرور هرمس</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            یک سرور آماده با ایجنت هرمس، از پیش نصب‌شده — اسکیل‌هایتان (برنامه‌نویسی، رصد اخبار، ...) را انتخاب کنید و تحویل بگیرید.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center" style={{ minHeight: '30vh' }}>
          <Spinner size="lg" />
        </div>
      ) : offerings.length === 0 ? (
        <EmptyState icon="rocket" title="در حال حاضر پلنی موجود نیست" description="لطفاً بعداً دوباره سر بزنید." />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: '1rem',
          }}
        >
          {offerings.map((o) => (
            <OfferingCard key={o.id} offering={o} loggedIn={!!user} />
          ))}
        </div>
      )}

      <div className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <div className="flex items-center gap-2">
          <Icon name="info" size={16} className="text-[var(--text-muted)]" />
          <span style={{ fontWeight: 600 }}>بعد از خرید چه اتفاقی می‌افتد؟</span>
        </div>
        <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', lineHeight: 1.8 }}>
          پس از پرداخت، سرور برای شما راه‌اندازی و اسکیل‌های انتخابی روی هرمس نصب می‌شود. سپس می‌توانید از
          صفحه‌ی مدیریت سرور، اسکیل‌های جدید اضافه یا اسکیل‌های موجود را حذف کنید و کلید API اختصاصی سرورتان
          را برای شارژ اعتبار مصرفی مدیریت نمایید.
        </p>
      </div>
    </div>
  )
}

function OfferingCard({ offering, loggedIn }: { offering: Offering; loggedIn: boolean }) {
  return (
    <div className="card card-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '1.25rem' }}>
      <div className="flex items-center justify-between">
        <span className="badge aurora-cap-default" style={{ fontSize: '0.6875rem' }}>
          {offering.arch === 'arm64' ? 'ARM' : 'Intel'}
        </span>
        {offering.included_credit > 0 && (
          <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
            + {faPrice(offering.included_credit)} اعتبار هدیه
          </span>
        )}
      </div>

      <h2 style={{ fontSize: 'var(--fs-md)', fontWeight: 700 }}>{offering.name_fa}</h2>
      <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>{offering.description_fa}</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.375rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        <span>{faNum(offering.vcpu)} هسته پردازشی</span>
        <span>{faNum(offering.ram_mb / 1024)} گیگابایت رم</span>
        <span>{faNum(offering.disk_gb)} گیگابایت دیسک</span>
        <span>{faNum(offering.traffic_tb)} ترابایت ترافیک</span>
        <span>تا {faNum(offering.max_skills)} اسکیل هم‌زمان</span>
      </div>

      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
        {offering.setup_price_irt > 0 && (
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            راه‌اندازی: {faPrice(offering.setup_price_irt)}
          </span>
        )}
        <span style={{ fontSize: 'var(--fs-lg)', fontWeight: 700, color: 'var(--accent)' }}>
          {faPrice(offering.monthly_price_irt)} <span style={{ fontSize: '0.75rem', fontWeight: 400, color: 'var(--text-muted)' }}>/ ماه</span>
        </span>
      </div>

      <Link
        href={loggedIn ? `/hermes/order?offering=${offering.id}` : '/login'}
        className="btn btn-primary"
        style={{ justifyContent: 'center' }}
      >
        <Icon name="rocket" size={16} />
        {loggedIn ? 'سفارش این سرور' : 'ورود برای سفارش'}
      </Link>
    </div>
  )
}
