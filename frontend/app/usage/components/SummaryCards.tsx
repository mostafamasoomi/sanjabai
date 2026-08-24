import Link from 'next/link'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { fmtToman, fmtTokens } from '../usageHelpers'
import { FadeInCard } from './FadeInCard'
import type { UsageData } from '../usageTypes'

/* ═══════════════════════════════════════════════════════════════════════════
   The four summary cards: balance, spent this month, total tokens, models
   used. Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function SummaryCards({ data, totalTokens }: { data: UsageData | null; totalTokens: number }) {
  return (
    <div className="usage-cards" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
      {/* Balance */}
      <FadeInCard className="card" delay={0} style={{ padding: 20, position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', top: 0, insetInlineStart: 0, insetInlineEnd: 0, height: 3, background: 'var(--accent)' }} />
        <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="wallet" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
          موجودی فعلی
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(data?.current_balance ?? 0)}</div>
        <Link href="/wallet" style={{ fontSize: 11, color: 'var(--accent)', marginTop: 8, display: 'inline-block' }}>شارژ کیف پول ←</Link>
      </FadeInCard>

      {/* Spent this month */}
      <FadeInCard className="card" delay={60} style={{ padding: 20 }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="payment" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
          مصرف این ماه
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(data?.total_spent_this_month ?? 0)}</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>{faNum(data?.event_count_this_month ?? 0)} درخواست</div>
      </FadeInCard>

      {/* Total tokens */}
      <FadeInCard className="card" delay={120} style={{ padding: 20 }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="sparkles" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
          کل توکن‌های مصرفی
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(totalTokens)}</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
          ورودی: {fmtTokens(data?.total_input_tokens_this_month ?? 0)} | خروجی: {fmtTokens(data?.total_output_tokens_this_month ?? 0)}
        </div>
      </FadeInCard>

      {/* Models used */}
      <FadeInCard className="card" delay={180} style={{ padding: 20 }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="models" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
          مدل‌های استفاده شده
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{faNum(data?.per_model_breakdown.length ?? 0)}</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>مدل فعال این ماه</div>
      </FadeInCard>
    </div>
  )
}
