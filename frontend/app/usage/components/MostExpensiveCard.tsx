import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { fmtTokens, fmtDate, modelName } from '../usageHelpers'
import { FadeInCard } from './FadeInCard'
import type { UsageEvent } from '../usageTypes'

/* ═══════════════════════════════════════════════════════════════════════════
   "Most expensive recent call" highlight. Split out of page.tsx verbatim --
   no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function MostExpensiveCard({ mostExpensive }: { mostExpensive: UsageEvent | null }) {
  if (!mostExpensive) return null
  return (
    <FadeInCard className="card" delay={220} style={{ marginBottom: 16, padding: 20, background: 'linear-gradient(135deg, rgba(99,102,241,0.10), rgba(139,92,246,0.04))', border: '1px solid var(--border-strong)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <div style={{ width: 44, height: 44, borderRadius: 'var(--radius-md)', background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Icon name="warning" size={22} style={{ color: 'var(--warning)' }} />
        </div>
        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 2 }}>گران‌ترین درخواست اخیر</div>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{modelName(mostExpensive.model)}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{fmtDate(mostExpensive.created_at)}</div>
        </div>
        <div style={{ textAlign: 'left' }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{faNum(mostExpensive.cost)}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFeatureSettings: '"tnum"' }}>
            {fmtTokens(mostExpensive.input_tokens)} ورودی / {fmtTokens(mostExpensive.output_tokens)} خروجی
          </div>
        </div>
      </div>
    </FadeInCard>
  )
}
