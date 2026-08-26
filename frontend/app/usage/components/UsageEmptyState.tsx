'use client'

import Link from 'next/link'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { usageEmptyStateStrings } from './UsageEmptyState.strings'
import { FadeInCard } from './FadeInCard'

/* ═══════════════════════════════════════════════════════════════════════════
   "No usage recorded yet" empty state. Split out of page.tsx verbatim -- no
   behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function UsageEmptyState() {
  const lang = useLang()
  const s = usageEmptyStateStrings(lang)

  return (
    <FadeInCard className="card" style={{ padding: '56px 24px', textAlign: 'center' }}>
      <div style={{ width: 96, height: 96, margin: '0 auto 24px', position: 'relative' }}>
        <div style={{ position: 'absolute', inset: 0, borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)' }} />
        <div style={{ position: 'absolute', inset: 22, borderRadius: 'var(--radius-full)', background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width={40} height={40} viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth={1.5} aria-hidden>
            <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" fill="var(--accent-dim)" stroke="var(--accent)" strokeLinejoin="round" />
          </svg>
        </div>
      </div>
      <h2 className="card-title" style={{ marginBottom: 8 }}>{s.title}</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: 14, maxWidth: 360, margin: '0 auto 24px' }}>
        {s.desc}
      </p>
      <Link href="/chat" className="btn btn-lg btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <Icon name="chat" size={16} />
        {s.startChat}
      </Link>
    </FadeInCard>
  )
}
