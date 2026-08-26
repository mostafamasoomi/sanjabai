'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { Spinner, EmptyState, toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { hermesLandingStrings } from './page.strings'

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
  description_en: string
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
  const lang = useLang()
  const s = hermesLandingStrings(lang)
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
        if (!cancelled) toast(s.loadError, 'error')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          <h1 className="page-title">{s.title}</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            {s.subtitle}
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center" style={{ minHeight: '30vh' }}>
          <Spinner size="lg" />
        </div>
      ) : offerings.length === 0 ? (
        <EmptyState icon="rocket" title={s.emptyTitle} description={s.emptyDescription} />
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
          <span style={{ fontWeight: 600 }}>{s.afterPurchaseTitle}</span>
        </div>
        <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', lineHeight: 1.8 }}>
          {s.afterPurchaseBody}
        </p>
      </div>
    </div>
  )
}

function OfferingCard({ offering, loggedIn }: { offering: Offering; loggedIn: boolean }) {
  const lang = useLang()
  const s = hermesLandingStrings(lang)
  const f = fmt(lang)
  const name = lang === 'en' ? offering.name_en : offering.name_fa
  const description = lang === 'en' ? offering.description_en : offering.description_fa

  return (
    <div className="card card-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '1.25rem' }}>
      <div className="flex items-center justify-between">
        <span className="badge aurora-cap-default" style={{ fontSize: '0.6875rem' }}>
          {offering.arch === 'arm64' ? 'ARM' : 'Intel'}
        </span>
        {offering.included_credit > 0 && (
          <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
            {s.includedCredit(f.price(offering.included_credit))}
          </span>
        )}
      </div>

      <h2 style={{ fontSize: 'var(--fs-md)', fontWeight: 700 }}>{name}</h2>
      <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>{description}</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.375rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        <span>{s.vcpu(f.num(offering.vcpu))}</span>
        <span>{s.ram(f.num(offering.ram_mb / 1024))}</span>
        <span>{s.disk(f.num(offering.disk_gb))}</span>
        <span>{s.traffic(f.num(offering.traffic_tb))}</span>
        <span>{s.maxSkills(f.num(offering.max_skills))}</span>
      </div>

      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
        {offering.setup_price_irt > 0 && (
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {s.setupFee(f.price(offering.setup_price_irt))}
          </span>
        )}
        <span style={{ fontSize: 'var(--fs-lg)', fontWeight: 700, color: 'var(--accent)' }}>
          {f.price(offering.monthly_price_irt)} <span style={{ fontSize: '0.75rem', fontWeight: 400, color: 'var(--text-muted)' }}>{s.perMonth}</span>
        </span>
      </div>

      <Link
        href={loggedIn ? `/hermes/order?offering=${offering.id}` : '/login'}
        className="btn btn-primary"
        style={{ justifyContent: 'center' }}
      >
        <Icon name="rocket" size={16} />
        {loggedIn ? s.orderThis : s.loginToOrder}
      </Link>
    </div>
  )
}
