'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import LineChart, { type LineChartSeries } from './charts/LineChart'
import { dayLabel, type TimeseriesData } from './AnalyticsCharts'
import { dashboardChartsStrings } from './DashboardCharts.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Two compact sparkline cards for the dashboard, replacing the AdminCharts
   stub («نمودارها در آپدیت بعدی فعال می‌شوند») that stood in for charts while
   recharts was being removed. recharts and every other charting library stay
   BANNED — the ban's full record is in AnalyticsCharts.tsx; this draws
   through the same hand-written SVG kit (./charts/LineChart).

   PRESENTATIONAL, no fetch of its own: `data` is the SAME
   GET /admin/analytics/timeseries?days=30 response DashboardSection.tsx
   fetches once and also feeds to DashboardAlerts / DashboardModelBreakdown
   and the promoted margin/coverage stat cards — one fetch, one source of
   truth, so a StatCard figure and this chart can never disagree. (Before
   this pass, DashboardCharts fetched the same URL independently and threw
   away everything except two of its ~12 fields; that duplicate request is
   gone now that the section needs the rest of the payload too.)

   Pinned to days=30: the dashboard is a glance, not an analysis. The window
   selector, cost/margin series and the tables live on the analytics page,
   reached through `onOpenAnalytics` — a CALLBACK, deliberately not an
   <a href="?page=analytics">: the admin token lives in memory only (see
   ../api.ts), so a real navigation would log the admin out. When the shell
   has not passed the callback down, the link is simply not rendered.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function DashboardCharts({ data, onOpenAnalytics }: { data: TimeseriesData; onOpenAnalytics?: () => void }) {
  const lang = useLang()
  const s = dashboardChartsStrings(lang)
  const f = fmt(lang)

  // Both series come zero-filled off the same date spine; index-aligned.
  const labels = data.daily_consumption.map((d) => dayLabel(d.day, lang))
  const consumption: LineChartSeries[] = [
    { id: 'consumption', metric: 'net', label: s.consumptionLegend, values: data.daily_consumption.map((d) => d.amount) },
  ]
  const newUsers: LineChartSeries[] = [
    { id: 'new-users', metric: 'users', label: s.newUsersLegend, values: data.daily_users.map((d) => d.new_users) },
  ]

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="admin-card">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-semibold text-sm text-primary flex items-center gap-2">
            <Icon name="chart" size={16} />
            {s.consumptionTitle}
          </h3>
          {onOpenAnalytics && (
            <button className="btn btn-sm" onClick={onOpenAnalytics}>
              <Icon name="chart" size={14} />
              <span>{s.openAnalytics}</span>
            </button>
          )}
        </div>
        <LineChart
          labels={labels}
          series={consumption}
          ariaLabel={s.consumptionAria}
          formatValue={f.price}
          height={90}
          maxXTicks={4}
        />
      </div>

      <div className="admin-card">
        <h3 className="font-semibold text-sm text-primary flex items-center gap-2 mb-3">
          <Icon name="profile" size={16} />
          {s.newUsersTitle}
        </h3>
        <LineChart
          labels={labels}
          series={newUsers}
          ariaLabel={s.newUsersAria}
          formatTick={(v) => f.num(v)}
          height={90}
          maxXTicks={4}
        />
      </div>
    </div>
  )
}
