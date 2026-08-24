'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { fmtPct } from '../usageHelpers'
import { FadeInCard } from './FadeInCard'
import { DonutChart } from './DonutChart'
import type { ModelStat } from '../usageTypes'

/* ═══════════════════════════════════════════════════════════════════════════
   Model cost distribution (this month, from the server's per_model_breakdown).
   The 30-day daily sparkline that used to sit beside this was removed: it
   bucketed the truncated 20-row recent_events list into 30 day-columns, so it
   under-counted every day for anyone with more than 20 events. The /me/usage
   endpoint exposes no server-side daily series, so there is nothing accurate
   to draw here yet.
   Split out of page.tsx verbatim -- no behaviour change (the `hoveredLegend`
   state used to live on the page and is now local to this card, since
   nothing else read it).
   ═══════════════════════════════════════════════════════════════════════════ */

export function ModelDistributionCard({
  modelStats,
  totalModelCost,
  donutData,
}: {
  modelStats: ModelStat[]
  totalModelCost: number
  donutData: { label: string; value: number; color: string }[]
}) {
  const [hoveredLegend, setHoveredLegend] = useState<number | null>(null)

  return (
    <div style={{ marginBottom: 16 }}>
      {/* Donut: model cost distribution */}
      <FadeInCard className="card" delay={260} style={{ padding: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="chart" size={16} className="text-accent" />
          <h2 className="card-title">توزیع هزینه مدل‌ها</h2>
        </div>
        {modelStats.length > 0 ? (
          <>
            <DonutChart
              data={donutData}
              centerValue={faNum(totalModelCost)}
              centerLabel="تومان"
            />
            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {modelStats.map((m, i) => (
                <div
                  key={m.model}
                  onMouseEnter={() => setHoveredLegend(i)}
                  onMouseLeave={() => setHoveredLegend(null)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    fontSize: 12,
                    padding: '4px 6px',
                    borderRadius: 'var(--radius-sm)',
                    background: hoveredLegend === i ? 'var(--bg-hover)' : 'transparent',
                    transition: 'background 0.15s ease',
                  }}
                >
                  <div style={{ width: 10, height: 10, borderRadius: 'var(--radius-full)', background: m.color, flexShrink: 0 }} />
                  <span style={{ flex: 1, color: 'var(--text-secondary)', fontWeight: 600 }}>{m.name}</span>
                  <span style={{ color: 'var(--text-muted)', fontFeatureSettings: '"tnum"' }}>{fmtPct(m.cost / totalModelCost)}</span>
                  <span style={{ color: 'var(--text-primary)', fontWeight: 700, fontFeatureSettings: '"tnum"', minWidth: 72, textAlign: 'left' }}>{faNum(m.cost)}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>داده‌ای برای نمایش نمودار وجود ندارد</div>
        )}
      </FadeInCard>
    </div>
  )
}
