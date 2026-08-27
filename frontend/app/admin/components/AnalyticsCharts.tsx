'use client'

import { useMemo } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang, type Lang } from '@/components/LanguageToggle'
import { fmt, type Formatters } from '@/lib/i18n'
import { toFaDigits } from '@/lib/format'
import { StatCard } from '../sections/shared'
import LineChart, { type LineChartSeries } from './charts/LineChart'
import BarChart, { type BarChartSeries } from './charts/BarChart'
import { metricColor } from './charts/chartTheme'
import { analyticsChartsStrings } from './AnalyticsCharts.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   The full analysis surface, rendering GET /admin/analytics/timeseries.
   recharts (and every other charting library) is BANNED in this project —
   its barrel optimization breaks the production build. That ban used to be
   documented here, carried over from the deleted AdminCharts.tsx stub that this file (plus DashboardCharts)
   replaced; the record now lives here. Everything below draws through the
   hand-written SVG kit in ./charts/.

   THE contract this screen exists to enforce (mirrored from the endpoint's
   docstring, backend/admin_analytics_timeseries.py):

     * `usage_margin`, `net` and per-row `margin` are NULL whenever their
       bucket is not fully cost-measured. NULL renders as «اندازه‌گیری‌نشده»
       — never as 0, and never as a line drawn straight through the gap.
       Every display of a nullable margin goes through `marginDisplay`, and
       every chart series carrying one goes through `usageMarginValues`;
       both are unit-tested (tests/lib/analyticsMargin.test.ts) so a future
       `?? 0` fails a test, not just a review.
     * `cost_coverage < 1` is said out loud (the warning card below), with
       `cost_cutover_at` explaining WHY the margin is missing.
     * revenue − cost is GROSS margin on upstream token cost, never called
       net profit — see AnalyticsCharts.strings.ts.

   Money values are RAW INTEGER TOMANS end to end; nothing here multiplies
   or divides an amount — the only arithmetic on the way to the screen is
   coverage ratio → percent, which is not money.
   ═══════════════════════════════════════════════════════════════════════════ */

// ─── Response shapes, mirrored from the endpoint ────────────────────────────

export interface DailyAmount { day: string; amount: number }
export interface DailyUsers { day: string; active_users: number; new_users: number }
export interface DailyTokens { day: string; input_tokens: number; output_tokens: number }
export interface DailyCost {
  day: string
  known_cost: number
  cost_coverage: number
  unknown_events: number
  error_events: number
}
export interface DailyMargin { day: string; usage_margin: number | null; net: number | null }
export interface DailyCount { day: string; count: number }
export interface DailyPurchasers { day: string; purchasers: number }
export interface ModelConsumptionRow {
  model: string
  consumption: number
  known_cost: number
  cost_coverage: number
  margin: number | null
  users: number
  calls: number
}
export interface TopUserRow {
  user_id: number
  email: string
  total_cost: number
  known_cost: number
  cost_coverage: number
  margin: number | null
  total_tokens: number
  calls: number
}
export interface AnalyticsTotals {
  consumption: number
  gateway_revenue: number
  known_cost: number
  cost_coverage: number
  usage_margin: number | null
  net: number | null
  unknown_events: number
  error_events: number
}
export interface TimeseriesData {
  days: number
  daily_consumption: DailyAmount[]
  daily_gateway_revenue: DailyAmount[]
  daily_users: DailyUsers[]
  daily_tokens: DailyTokens[]
  daily_cost: DailyCost[]
  daily_margin: DailyMargin[]
  daily_conversations: DailyCount[]
  daily_purchasers: DailyPurchasers[]
  consumption_by_model: ModelConsumptionRow[]
  top_users: TopUserRow[]
  totals: AnalyticsTotals
  cost_cutover_at: string | null
}

// ─── Pure helpers (unit-tested; keep them free of React) ────────────────────

/** Short day label from a `YYYY-MM-DD` string, e.g. «۲۱ مرداد» (fa) or
 *  "21 Aug" (en). Same idiom the previous AnalyticsSection chart used. */
export function dayLabel(dateStr: string, lang: Lang): string {
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  if (lang === 'en') {
    return d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric' })
  }
  return toFaDigits(d.toLocaleDateString('fa-IR', { month: 'short', day: 'numeric' }))
}

/** THE null-margin rule, in one place. A null/undefined margin means the
 *  bucket is not fully cost-measured, and the ONLY honest rendering is the
 *  `unmeasured` word. Rewriting this to `price(margin ?? 0)` would show
 *  «۰ تومان» for every pre-cutover day — a fake break-even past — which is
 *  exactly what tests/lib/analyticsMargin.test.ts fails on. */
export function marginDisplay(
  margin: number | null | undefined,
  price: (v: number) => string,
  unmeasured: string,
): string {
  if (margin == null || !Number.isFinite(margin)) return unmeasured
  return price(margin)
}

/** Coverage arrives as a 0..1 ratio; percent formatters take 0..100. Ratio
 *  scaling, not money scaling. */
export function coverageDisplay(coverage: number, percent: Formatters['percent']): string {
  return percent(coverage * 100)
}

/** Chart values for the daily gross margin, PRESERVING nulls: the kit draws
 *  a null as a gap in the line, which is the truthful picture of an
 *  unmeasured day. Mapping through `?? 0` here would draw the fake flat
 *  line the whole contract forbids — also covered by the unit test. */
export function usageMarginValues(rows: DailyMargin[]): (number | null)[] {
  return rows.map((r) => r.usage_margin)
}

// ─── Presentational bits ────────────────────────────────────────────────────

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="admin-card">
      <h3 className="font-semibold text-sm mb-3 text-primary flex items-center gap-2">
        <Icon name="chart" size={16} />
        {title}
      </h3>
      {children}
    </div>
  )
}

export default function AnalyticsCharts({ data }: { data: TimeseriesData }) {
  const lang = useLang()
  const s = analyticsChartsStrings(lang)
  const f = fmt(lang)

  // Every daily series is zero-filled from the same date spine by the
  // backend (one generate_series CTE), so aligning by index is aligning by
  // day.
  const labels = useMemo(
    () => data.daily_consumption.map((d) => dayLabel(d.day, lang)),
    [data, lang],
  )

  const moneySeries = useMemo<LineChartSeries[]>(() => [
    // 'net' here borrows the brand-accent slot of the palette for the
    // headline consumption line; the semantic net-profit series is not
    // drawn (see the margin rule above — most of it is null today anyway).
    { id: 'consumption', metric: 'net', label: s.legendConsumption, values: data.daily_consumption.map((d) => d.amount) },
    { id: 'gateway', metric: 'revenue', label: s.legendGateway, values: data.daily_gateway_revenue.map((d) => d.amount) },
    { id: 'cost', metric: 'cost', label: s.legendKnownCost, values: data.daily_cost.map((d) => d.known_cost) },
    // Nullable and allowed to go negative — the kit draws below-zero values
    // under a strengthened zero line, and nulls as gaps.
    { id: 'margin', metric: 'margin', label: s.legendMargin, values: usageMarginValues(data.daily_margin) },
  ], [data, s])

  const growthSeries = useMemo<BarChartSeries[]>(() => [
    { id: 'new-users', metric: 'users', label: s.legendNewUsers, values: data.daily_users.map((d) => d.new_users) },
    // Buyers are people whose money actually arrived — money-in green.
    { id: 'purchasers', metric: 'revenue', label: s.legendPurchasers, values: data.daily_purchasers.map((d) => d.purchasers) },
  ], [data, s])

  const convSeries = useMemo<LineChartSeries[]>(() => [
    { id: 'conversations', metric: 'conversations', label: s.legendConversations, values: data.daily_conversations.map((d) => d.count) },
  ], [data, s])

  const tokenSeries = useMemo<BarChartSeries[]>(() => [
    { id: 'input-tokens', metric: 'tokens', label: s.legendInputTokens, values: data.daily_tokens.map((d) => d.input_tokens) },
    { id: 'output-tokens', metric: 'conversations', label: s.legendOutputTokens, values: data.daily_tokens.map((d) => d.output_tokens) },
  ], [data, s])

  const t = data.totals
  const partiallyMeasured = t.cost_coverage < 1

  return (
    <div className="space-y-6">
      {/* KPI row — the margin card honours the null rule via marginDisplay. */}
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        <StatCard icon="chart" label={s.kpiConsumption} value={f.price(t.consumption)} color={metricColor('net')} />
        <StatCard icon="payment" label={s.kpiGateway} value={f.price(t.gateway_revenue)} color={metricColor('revenue')} />
        <StatCard icon="wallet" label={s.kpiKnownCost} value={f.price(t.known_cost)} color={metricColor('cost')} />
        <StatCard
          icon="chart"
          label={s.kpiMargin}
          value={marginDisplay(t.usage_margin, f.price, s.unmeasured)}
          color={metricColor('margin')}
        />
      </div>
      <p className="text-xs text-muted">{s.marginDisclaimer}</p>

      {/* Partial coverage is said out loud, with the cutover date explaining
          WHY the margin is missing — never a silent gap. */}
      {partiallyMeasured && (
        <div className="admin-card" style={{ borderRight: '3px solid var(--warning)' }}>
          <div className="flex items-start gap-3">
            <Icon name="warning" size={18} style={{ color: 'var(--warning)' }} />
            <div className="text-xs text-secondary space-y-1 min-w-0">
              <p className="text-sm font-medium text-primary">{s.coverageTitle}</p>
              <p>{s.coverageBody(coverageDisplay(t.cost_coverage, f.percent))}</p>
              {data.cost_cutover_at && <p>{s.cutoverNote(f.date(data.cost_cutover_at))}</p>}
              {(t.unknown_events > 0 || t.error_events > 0) && (
                <p>{s.eventCounts(f.num(t.unknown_events), f.num(t.error_events))}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Money on ONE shared scale, so cost near zero looks near zero. */}
      <ChartCard title={s.moneyTitle}>
        <LineChart labels={labels} series={moneySeries} ariaLabel={s.moneyAria} formatValue={f.price} height={200} />
      </ChartCard>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title={s.growthTitle}>
          <BarChart labels={labels} series={growthSeries} mode="grouped" ariaLabel={s.growthAria} formatTick={(v) => f.num(v)} />
        </ChartCard>
        <ChartCard title={s.convTitle}>
          <LineChart labels={labels} series={convSeries} ariaLabel={s.convAria} formatTick={(v) => f.num(v)} />
        </ChartCard>
      </div>

      <ChartCard title={s.tokensTitle}>
        <BarChart labels={labels} series={tokenSeries} mode="stacked" ariaLabel={s.tokensAria} />
      </ChartCard>

      {/* Per-model table — margin column under the same null rule. */}
      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-3 text-primary">{s.modelTableTitle}</h3>
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="p-3">{s.colModel}</th>
                <th className="p-3">{s.colConsumption}</th>
                <th className="p-3">{s.colKnownCost}</th>
                <th className="p-3">{s.colCoverage}</th>
                <th className="p-3">{s.colMargin}</th>
                <th className="p-3">{s.colUsers}</th>
                <th className="p-3">{s.colCalls}</th>
              </tr>
            </thead>
            <tbody>
              {data.consumption_by_model.length === 0 ? (
                <tr><td colSpan={7} className="p-6 text-center text-sm text-muted">{s.noRows}</td></tr>
              ) : (
                data.consumption_by_model.map((row) => (
                  <tr key={row.model}>
                    <td className="p-3 text-xs font-mono" dir="ltr">{row.model}</td>
                    <td className="p-3">{f.price(row.consumption)}</td>
                    <td className="p-3">{f.price(row.known_cost)}</td>
                    <td className="p-3">{coverageDisplay(row.cost_coverage, f.percent)}</td>
                    <td className={`p-3${row.margin == null ? ' text-muted' : ''}`}>
                      {marginDisplay(row.margin, f.price, s.unmeasured)}
                    </td>
                    <td className="p-3">{f.num(row.users)}</td>
                    <td className="p-3">{f.num(row.calls)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Per-user table — same shape, same rule. */}
      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-3 text-primary">{s.userTableTitle}</h3>
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="p-3">{s.colUser}</th>
                <th className="p-3">{s.colConsumption}</th>
                <th className="p-3">{s.colKnownCost}</th>
                <th className="p-3">{s.colCoverage}</th>
                <th className="p-3">{s.colMargin}</th>
                <th className="p-3">{s.colTokens}</th>
                <th className="p-3">{s.colCalls}</th>
              </tr>
            </thead>
            <tbody>
              {data.top_users.length === 0 ? (
                <tr><td colSpan={7} className="p-6 text-center text-sm text-muted">{s.noRows}</td></tr>
              ) : (
                data.top_users.map((row) => (
                  <tr key={row.user_id}>
                    <td className="p-3 text-xs font-mono" dir="ltr">{row.email}</td>
                    <td className="p-3">{f.price(row.total_cost)}</td>
                    <td className="p-3">{f.price(row.known_cost)}</td>
                    <td className="p-3">{coverageDisplay(row.cost_coverage, f.percent)}</td>
                    <td className={`p-3${row.margin == null ? ' text-muted' : ''}`}>
                      {marginDisplay(row.margin, f.price, s.unmeasured)}
                    </td>
                    <td className="p-3">{f.num(row.total_tokens)}</td>
                    <td className="p-3">{f.num(row.calls)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
