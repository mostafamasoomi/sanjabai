'use client'

import Link from 'next/link'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { fmtToman, fmtTokens } from '../usageHelpers'
import { summaryCardsStrings } from './SummaryCards.strings'
import { FadeInCard } from './FadeInCard'
import type { UsageData } from '../usageTypes'

/* ═══════════════════════════════════════════════════════════════════════════
   The four summary cards: balance, spent this month, total tokens, models
   used. Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function SummaryCards({ data, totalTokens }: { data: UsageData | null; totalTokens: number }) {
  const lang = useLang()
  const s = summaryCardsStrings(lang)
  const f = fmt(lang)

  return (
    <div className="usage-cards" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
      {/* Balance */}
      <FadeInCard className="card" delay={0} style={{ padding: 20, position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', top: 0, insetInlineStart: 0, insetInlineEnd: 0, height: 3, background: 'var(--accent)' }} />
        <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="wallet" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
          {s.balance}
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(data?.current_balance ?? 0, lang)}</div>
        <Link href="/wallet" style={{ fontSize: 11, color: 'var(--accent)', marginTop: 8, display: 'inline-block' }}>{s.topUp}</Link>
      </FadeInCard>

      {/* Spent this month */}
      <FadeInCard className="card" delay={60} style={{ padding: 20 }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="payment" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
          {s.spentThisMonth}
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(data?.total_spent_this_month ?? 0, lang)}</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>{s.requestsCount(f.num(data?.event_count_this_month ?? 0))}</div>
      </FadeInCard>

      {/* Total tokens */}
      <FadeInCard className="card" delay={120} style={{ padding: 20 }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="sparkles" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
          {s.totalTokens}
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(totalTokens, lang)}</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
          {s.ioTokens(fmtTokens(data?.total_input_tokens_this_month ?? 0, lang), fmtTokens(data?.total_output_tokens_this_month ?? 0, lang))}
        </div>
      </FadeInCard>

      {/* Models used */}
      <FadeInCard className="card" delay={180} style={{ padding: 20 }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="models" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
          {s.modelsUsed}
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{f.num(data?.per_model_breakdown.length ?? 0)}</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>{s.activeThisMonth}</div>
      </FadeInCard>
    </div>
  )
}
