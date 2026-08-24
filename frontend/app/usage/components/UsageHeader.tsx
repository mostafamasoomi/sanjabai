import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Page header: title + export/refresh actions, and the "this month" scope
   note. Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function UsageHeader({
  hasAnyData,
  refreshing,
  onExport,
  onRefresh,
}: {
  hasAnyData: boolean
  refreshing: boolean
  onExport: () => void
  onRefresh: () => void
}) {
  return (
    <>
      <div className="usage-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24, gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="chart" size={18} className="text-accent" />
          </div>
          <div>
            <h1 className="page-title">گزارش مصرف</h1>
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>تحلیل هزینه، توکن و عملکرد مدل‌ها</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            className="btn btn-sm btn-secondary"
            onClick={onExport}
            disabled={!hasAnyData}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            aria-label="خروجی CSV"
          >
            <Icon name="external" size={14} />
            خروجی CSV
          </button>
          <button
            className="btn btn-sm btn-secondary"
            onClick={onRefresh}
            disabled={refreshing}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <Icon name="refresh" size={14} className={refreshing ? 'spin' : ''} />
            بروزرسانی
          </button>
        </div>
      </div>

      {/* Scope note. Totals below are the server's authoritative current-month
          aggregates; the events table shows only the latest events. There is no
          week/all-time toggle any more — those were computed by bucketing the
          truncated 20-row recent_events list and were silently wrong for anyone
          with more history. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        <Icon name="calendar" size={16} className="text-muted" />
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>آمار این ماه</span>
      </div>
    </>
  )
}
