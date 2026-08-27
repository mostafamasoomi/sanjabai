'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { useAdminResource } from '../useAdminResource'
import { CardSkeleton, ErrorCard } from '../sections/LoadState'
import LineChart, { type LineChartSeries } from './charts/LineChart'
import { dayLabel, type DailyAmount, type DailyUsers } from './AnalyticsCharts'
import { dashboardChartsStrings } from './DashboardCharts.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Two compact sparkline cards for the dashboard, replacing the AdminCharts
   stub («نمودارها در آپدیت بعدی فعال می‌شوند») that stood in for charts while
   recharts was being removed. recharts and every other charting library stay
   BANNED — the ban's full record is in AnalyticsCharts.tsx; this draws
   through the same hand-written SVG kit (./charts/LineChart).

   Pinned to days=30: the dashboard is a glance, not an analysis. The window
   selector, cost/margin series and the tables live on the analytics page,
   reached through `onOpenAnalytics` — a CALLBACK, deliberately not an
   <a href="?page=analytics">: the admin token lives in memory only (see
   ../api.ts), so a real navigation would log the admin out. When the shell
   has not passed the callback down, the link is simply not rendered.
   ═══════════════════════════════════════════════════════════════════════════ */

interface SparklineData {
  daily_consumption: DailyAmount[]
  daily_users: DailyUsers[]
}

export default function DashboardCharts({ onOpenAnalytics }: { onOpenAnalytics?: () => void }) {
  const lang = useLang()
  const s = dashboardChartsStrings(lang)
  const f = fmt(lang)

  const { data, error, loading, reload } = useAdminResource<SparklineData>(
    '/api/admin/analytics/timeseries?days=30',
    (raw) => ({
      daily_consumption: (raw?.daily_consumption ?? []) as DailyAmount[],
      daily_users: (raw?.daily_users ?? []) as DailyUsers[],
    }),
    s.loadError,
  )

  if (error) return <ErrorCard message={error} onRetry={reload} />
  if (loading && !data) return <CardSkeleton count={2} />
  if (!data) return null

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
