'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { coverageDisplay, marginDisplay, type TimeseriesData } from './AnalyticsCharts'
import { dashboardModelBreakdownStrings } from './DashboardModelBreakdown.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Compact per-model mini-table for the dashboard glance page — the top 5
   rows of the SAME `consumption_by_model` array AnalyticsCharts.tsx's full
   table renders (already sorted by consumption desc, already carrying
   per-row `cost_coverage`/`margin` from the backend's `_with_margin`
   helper). No new fetch, no divergent numbers: `data` is the same
   GET /admin/analytics/timeseries?days=30 response DashboardSection.tsx
   passes to DashboardCharts and DashboardAlerts.

   `onOpenAnalytics` is the same in-memory-token-safe callback used by
   DashboardCharts — see that file's header comment for why this is never an
   <a href>.
   ═══════════════════════════════════════════════════════════════════════════ */

const TOP_N = 5

export default function DashboardModelBreakdown({
  data,
  onOpenAnalytics,
}: {
  data: TimeseriesData
  onOpenAnalytics?: () => void
}) {
  const lang = useLang()
  const s = dashboardModelBreakdownStrings(lang)
  const f = fmt(lang)

  const rows = data.consumption_by_model.slice(0, TOP_N)
  const remaining = data.consumption_by_model.length - rows.length

  return (
    <div className="admin-card">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="font-semibold text-sm text-primary flex items-center gap-2">
          <Icon name="chart" size={16} />
          {s.title}
        </h3>
        {onOpenAnalytics && (
          <button className="btn btn-sm" onClick={onOpenAnalytics}>
            <Icon name="chart" size={14} />
            <span>{s.openAnalytics}</span>
          </button>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="admin-table w-full text-sm">
          <thead>
            <tr>
              <th className="p-3">{s.colModel}</th>
              <th className="p-3">{s.colConsumption}</th>
              <th className="p-3">{s.colCoverage}</th>
              <th className="p-3">{s.colMargin}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="p-6 text-center text-sm text-muted">{s.noRows}</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.model}>
                  <td className="p-3 text-xs font-mono" dir="ltr">{row.model}</td>
                  <td className="p-3">{f.price(row.consumption)}</td>
                  <td className="p-3">{coverageDisplay(row.cost_coverage, f.percent)}</td>
                  <td className={`p-3${row.margin == null ? ' text-muted' : ''}`}>
                    {marginDisplay(row.margin, f.price, s.unmeasured)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {remaining > 0 && (
        <p className="text-xs text-muted mt-2">{s.moreRows(f.num(remaining))}</p>
      )}
    </div>
  )
}
