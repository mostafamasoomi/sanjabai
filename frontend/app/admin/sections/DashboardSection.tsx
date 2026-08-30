'use client'

import dynamic from 'next/dynamic'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt, type Formatters } from '@/lib/i18n'
import { StatCard, SectionHeader } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { useAdminResource } from '../useAdminResource'
import type { Analytics } from '../types'
import { dashboardStrings } from './DashboardSection.strings'
import { coverageDisplay, marginDisplay, type AnalyticsTotals, type TimeseriesData } from '../components/AnalyticsCharts'
import { metricColor } from '../components/charts/chartTheme'
import DashboardAlerts from '../components/DashboardAlerts'
import DashboardModelBreakdown from '../components/DashboardModelBreakdown'

const DashboardCharts = dynamic(() => import('../components/DashboardCharts'), { ssr: false })

/* ═══════════════════════════════════════════════════════════════════════════
   Dashboard — the admin's "نگاه اجمالی" glance page. Two independent GETs,
   each fetched here rather than handed down from AdminPanel's old loadAll(),
   each with its own loading/error/retry (see useAdminResource's "three
   distinguishable states, never two" contract):

     GET /admin/analytics                    -> `analytics` (headline totals
         + recent ledger rows)
     GET /admin/analytics/timeseries?days=30 -> `series` (the SAME payload
         the full Analytics deep-dive reads from, pinned to 30 days here —
         "the dashboard is a glance, not an analysis"). Fetched ONCE and fed
         to DashboardCharts, DashboardAlerts, DashboardModelBreakdown and the
         promoted margin/coverage/returning-purchaser stat cards below, so
         none of them can ever show a different 30-day figure than another —
         before this pass DashboardCharts fetched this same URL a second
         time and threw away everything but two of its ~12 fields.

   A failed load says so instead of sitting on the skeleton forever.

   Money is integer toman and renders through f.price; counts through f.num.
   Nullable margin/coverage/rate figures go through the SAME null-honesty
   helpers the analytics deep-dive uses (`marginDisplay`/`coverageDisplay`,
   imported from AnalyticsCharts.tsx, never reimplemented) — a bucket that is
   not fully cost-measured renders «اندازه‌گیری‌نشده», never ۰.

   `onOpenAnalytics` lets the sparkline/alerts/model-breakdown cards jump to
   the full analytics section without a navigation (an href would reload the
   page and drop the in-memory admin token — see ../api.ts). The shell wires
   it: `<DashboardSection onOpenAnalytics={() => setPage('analytics')} />` in
   AdminPanel.tsx; until it does, the links simply do not render.
   ═══════════════════════════════════════════════════════════════════════════ */

/** `totals` plus three churn-proxy fields a parallel backend change is
 *  adding to the SAME `/admin/analytics/timeseries` endpoint
 *  (`new_purchasers`, `returning_purchasers`, `returning_purchaser_rate`).
 *  Declared locally and optional: the live endpoint may not carry them yet,
 *  and every read below is null/undefined-safe (see `nullableRateDisplay`).
 *  `returning_purchaser_rate` is null when the window had zero purchasers —
 *  same honest treatment as a null margin, never rendered as ۰٪. */
interface TotalsWithChurn extends AnalyticsTotals {
  new_purchasers?: number
  returning_purchasers?: number
  returning_purchaser_rate?: number | null
}

type DashboardTimeseries = Omit<TimeseriesData, 'totals'> & { totals: TotalsWithChurn }

/** Same null-honesty convention as `marginDisplay` (AnalyticsCharts.tsx),
 *  adapted for a 0..1 ratio instead of a money figure. `null`/`undefined`
 *  both render the same honest word — never «۰٪», which would falsely claim
 *  a measured all-new-purchaser window (or, before the backend field ships,
 *  a measured anything at all). */
function nullableRateDisplay(
  rate: number | null | undefined,
  percent: Formatters['percent'],
  unmeasured: string,
): string {
  if (rate == null || !Number.isFinite(rate)) return unmeasured
  return percent(rate * 100, 0, unmeasured)
}

export default function DashboardSection({ onOpenAnalytics }: { onOpenAnalytics?: () => void }) {
  const lang = useLang()
  const s = dashboardStrings(lang)
  const f = fmt(lang)

  const { data: analytics, error: analyticsError, loading: analyticsLoading, reload: reloadAnalytics } = useAdminResource<Analytics>(
    '/api/admin/analytics',
    (raw) => raw as Analytics,
    s.loadError,
  )

  const { data: series, error: seriesError, loading: seriesLoading, reload: reloadSeries } = useAdminResource<DashboardTimeseries>(
    '/api/admin/analytics/timeseries?days=30',
    (raw) => raw as DashboardTimeseries,
    s.seriesLoadError,
  )

  const reload = () => { reloadAnalytics(); reloadSeries() }
  const totals = series?.totals
  const recentLedger = analytics?.recent_ledger || []

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title={s.title} subtitle={s.subtitle} />
        <RefreshButton onClick={reload} busy={analyticsLoading || seriesLoading} />
      </div>

      {analyticsError && <ErrorCard message={analyticsError} onRetry={reloadAnalytics} />}
      {seriesError && <ErrorCard message={seriesError} onRetry={reloadSeries} />}

      {!analyticsError && !analytics && <CardSkeleton count={5} />}

      {analytics && (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
          <StatCard icon="profile" label={s.totalUsers} value={f.num(analytics.user_count)} color="var(--accent)" />
          <StatCard icon="check" label={s.activeUsers} value={f.num(analytics.active_users)} color="var(--positive)" />
          {/* f.price already carries the unit word — the label must not
              repeat it, and nothing here scales the raw toman figure. */}
          <StatCard icon="payment" label={s.totalRevenue} value={f.price(analytics.total_revenue, { fallback: s.zeroPrice })} color="var(--info)" />
          <StatCard icon="code" label={s.tokensUsed} value={f.num(analytics.total_tokens, { fallback: s.zeroCount })} color="var(--warning)" />
          <StatCard icon="chat" label={s.conversations} value={f.num(analytics.conv_count, { fallback: s.zeroCount })} color="var(--accent)" />
          <StatCard
            icon="chart"
            label={s.usageMargin}
            value={totals ? marginDisplay(totals.usage_margin, f.price, s.unmeasured) : s.pending}
            color={metricColor('margin')}
          />
          <StatCard
            icon="chart"
            label={s.costCoverage}
            value={totals ? coverageDisplay(totals.cost_coverage, f.percent) : s.pending}
            color={metricColor('cost')}
          />
          <StatCard
            icon="profile"
            label={s.returningPurchaserRate}
            value={totals ? nullableRateDisplay(totals.returning_purchaser_rate, f.percent, s.unmeasured) : s.pending}
            color="var(--accent-purple)"
          />
        </div>
      )}

      {!seriesError && !series && <CardSkeleton count={2} />}

      {series && (
        <>
          <DashboardCharts data={series} onOpenAnalytics={onOpenAnalytics} />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <DashboardAlerts data={series} />
            <DashboardModelBreakdown data={series} onOpenAnalytics={onOpenAnalytics} />
          </div>
        </>
      )}

      {/* Collapsed by default — the highest-traffic glance information now
          lives above (stat cards, alerts, model breakdown); the raw ledger
          tail is one click away rather than always taking its own screen of
          vertical space. */}
      {analytics && (
        <details className="admin-card">
          <summary className="cursor-pointer font-medium text-primary flex items-center gap-2">
            <Icon name="history" size={18} className="text-secondary" />
            <span>{s.recentTransactions}</span>
            <span className="text-xs text-muted">{s.transactionCount(f.num(recentLedger.length))}</span>
          </summary>
          <div className="overflow-x-auto mt-4">
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="p-3">{s.colUserId}</th>
                  <th className="p-3">{s.colAmount}</th>
                  <th className="p-3">{s.colDescription}</th>
                  <th className="p-3">{s.colDate}</th>
                </tr>
              </thead>
              <tbody>
                {recentLedger.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-6 text-center text-sm text-muted">
                      {s.noTransactions}
                    </td>
                  </tr>
                ) : (
                  recentLedger.map((l) => (
                    <tr key={l.id}>
                      <td className="p-3 text-xs font-mono">{l.user_id}</td>
                      <td className="p-3">
                        <span className={l.amount > 0 ? 'badge badge-positive' : 'badge badge-danger'}>
                          {f.price(l.amount, { signed: true })}
                        </span>
                      </td>
                      <td className="p-3 text-xs text-secondary">{l.reason}</td>
                      <td className="p-3 text-xs text-muted">{f.date(l.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  )
}
