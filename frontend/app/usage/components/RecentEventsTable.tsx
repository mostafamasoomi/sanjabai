import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { fmtTokens, fmtDate, modelName } from '../usageHelpers'
import { FadeInCard } from './FadeInCard'
import type { UsageEvent } from '../usageTypes'

/* ═══════════════════════════════════════════════════════════════════════════
   Recent events table — the server returns at most the latest 20 rows, so
   the heading says exactly that rather than "تاریخچه مصرف" (which implied a
   complete history). The full history is available via the CSV export.
   Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function RecentEventsTable({ recentEvents }: { recentEvents: UsageEvent[] }) {
  return (
    <FadeInCard className="card overflow-hidden" delay={440}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Icon name="chart" size={16} className="text-accent" />
        <h2 className="card-title">۲۰ رویداد اخیر</h2>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', marginInlineStart: 'auto' }}>{faNum(recentEvents.length)} مورد</span>
      </div>

      {recentEvents.length === 0 ? (
        <div style={{ padding: 48, textAlign: 'center' }}>
          <Icon name="info" size={32} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>رویدادی ثبت نشده است</p>
        </div>
      ) : (
        <>
          {/* Table header */}
          <div className="usage-table-head" style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 90px 110px', gap: 8, padding: '10px 20px', borderBottom: '1px solid var(--border)', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>
            <div>مدل</div>
            <div>ورودی</div>
            <div>خروجی</div>
            <div>هزینه</div>
            <div>تاریخ</div>
          </div>
          {/* Table rows */}
          <div className="usage-table-body">
            {recentEvents.map((evt, idx) => (
              <div
                key={evt.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 80px 80px 90px 110px',
                  gap: 8,
                  padding: '10px 20px',
                  borderBottom: idx < recentEvents.length - 1 ? '1px solid var(--border)' : 'none',
                  fontSize: 13,
                  alignItems: 'center',
                  transition: 'background 0.15s ease',
                }}
                className="usage-row"
              >
                <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{modelName(evt.model)}</div>
                <div style={{ color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(evt.input_tokens)}</div>
                <div style={{ color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(evt.output_tokens)}</div>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{faNum(evt.cost)}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{fmtDate(evt.created_at)}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </FadeInCard>
  )
}
