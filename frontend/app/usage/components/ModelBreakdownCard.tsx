import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { fmtToman, fmtTokens } from '../usageHelpers'
import { FadeInCard } from './FadeInCard'
import type { ModelStat } from '../usageTypes'

/* ═══════════════════════════════════════════════════════════════════════════
   Per-model breakdown with token efficiency. Split out of page.tsx verbatim
   -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function ModelBreakdownCard({
  hasBreakdown,
  modelStats,
  maxModelCost,
}: {
  hasBreakdown: boolean
  modelStats: ModelStat[]
  maxModelCost: number
}) {
  if (!hasBreakdown) return null
  return (
    <FadeInCard className="card" delay={380} style={{ marginBottom: 16, overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Icon name="models" size={16} className="text-accent" />
        <h2 className="card-title">مصرف به تفکیک مدل</h2>
      </div>

      <div style={{ padding: '20px 20px 8px' }}>
        {modelStats.map((m) => {
          const pct = (m.cost / maxModelCost) * 100
          return (
            <div key={m.model} style={{ marginBottom: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6, flexWrap: 'wrap', gap: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: 'var(--radius-full)', background: m.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{m.name}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>({m.calls} درخواست)</span>
                </div>
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(m.cost)}</span>
              </div>
              <div style={{ height: 8, borderRadius: 4, background: 'var(--border)', overflow: 'hidden' }}>
                <div style={{ width: `${pct}%`, height: '100%', borderRadius: 4, background: m.color, transition: 'width 0.6s ease' }} />
              </div>
              <div style={{ display: 'flex', gap: 16, marginTop: 6, fontSize: 11, color: 'var(--text-muted)', flexWrap: 'wrap' }}>
                <span>ورودی: {fmtTokens(m.input_tokens)}</span>
                <span>خروجی: {fmtTokens(m.output_tokens)}</span>
                <span className="text-accent">
                  <Icon name="compare" size={11} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 3 }} />
                  میانگین: {fmtTokens(Math.round(m.avgTokensPerCall))} توکن/درخواست
                </span>
                <span>هزینه/درخواست: {faNum(Math.round(m.costPerCall))}</span>
              </div>
            </div>
          )
        })}
      </div>
    </FadeInCard>
  )
}
