'use client'

import { useMemo } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang, type Lang } from '@/components/LanguageToggle'
import { fmt, type Formatters } from '@/lib/i18n'
import { coverageDisplay, dayLabel, type DailyCost, type TimeseriesData } from './AnalyticsCharts'
import { dashboardAlertsStrings } from './DashboardAlerts.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Action-oriented alerts card for the dashboard glance page. Every alert is
   derived PURELY from the GET /admin/analytics/timeseries?days=30 payload
   DashboardSection.tsx already fetched for the charts/stat cards — no new
   request, no number invented here that the backend did not already return.

   Three checks, each producing at most a few lines:

     1. Any model in `consumption_by_model` with a MEASURED negative margin
        (margin != null && margin < 0) — the same null-honesty rule as
        everywhere else applies in reverse: an unmeasured margin is not an
        alert, because it is not known to be bad.
     2. The window's overall `cost_coverage` below MIN_COST_COVERAGE.
        AnalyticsCharts.tsx already warns on ANY coverage < 1 (fresh events
        that have not finished cost-accounting yet), which is too noisy for
        an action list. 0.8 is a UI judgment call, not a backend contract —
        picked as a round "meaningfully incomplete" line, documented here
        and in the handoff report.
     3. A per-day spike in `error_events` / `unknown_events` in `daily_cost`:
        a day clearing both an absolute floor (noise filter for low-volume
        days) and a multiple of the window's per-day average. Also a UI
        judgment call — see findSpikeDay below.

   If none of the three fire, the card shows a calm empty state — never a
   fabricated alert to avoid looking empty.
   ═══════════════════════════════════════════════════════════════════════════ */

/** UI-chosen thresholds — not a backend contract. See the file header. */
export const ALERT_THRESHOLDS = {
  /** Below this ratio (0..1), the window's cost coverage becomes an alert. */
  minCostCoverage: 0.8,
  /** A day's error/unknown count must clear this floor to be call-out-able
   *  at all, regardless of how it compares to the average. */
  minEventFloor: 3,
  /** ...and be at least this many times the window's per-day average. */
  spikeMultiplier: 2,
} as const

export interface AlertItem {
  id: string
  text: string
}

function findSpikeDay(
  rows: DailyCost[],
  key: 'error_events' | 'unknown_events',
): { day: string; value: number } | null {
  if (rows.length === 0) return null
  const total = rows.reduce((sum, r) => sum + r[key], 0)
  if (total === 0) return null
  const avg = total / rows.length
  let worst: { day: string; value: number } | null = null
  for (const r of rows) {
    const value = r[key]
    if (value < ALERT_THRESHOLDS.minEventFloor) continue
    if (avg > 0 && value < avg * ALERT_THRESHOLDS.spikeMultiplier) continue
    if (!worst || value > worst.value) worst = { day: r.day, value }
  }
  return worst
}

/** Pure, exported so it stays easy to unit-test later — mirrors the idiom of
 *  AnalyticsCharts.tsx's `marginDisplay`/`coverageDisplay`: no React here. */
export function deriveAlerts(
  data: TimeseriesData,
  s: ReturnType<typeof dashboardAlertsStrings>,
  f: Formatters,
  lang: Lang,
): AlertItem[] {
  const alerts: AlertItem[] = []

  for (const row of data.consumption_by_model) {
    if (row.margin != null && row.margin < 0) {
      alerts.push({ id: `margin-${row.model}`, text: s.negativeMargin(row.model, f.price(row.margin)) })
    }
  }

  if (data.totals.cost_coverage < ALERT_THRESHOLDS.minCostCoverage) {
    alerts.push({ id: 'coverage', text: s.lowCoverage(coverageDisplay(data.totals.cost_coverage, f.percent)) })
  }

  const errorSpike = findSpikeDay(data.daily_cost, 'error_events')
  if (errorSpike) {
    alerts.push({ id: 'error-spike', text: s.errorSpike(dayLabel(errorSpike.day, lang), f.num(errorSpike.value)) })
  }
  const unknownSpike = findSpikeDay(data.daily_cost, 'unknown_events')
  if (unknownSpike) {
    alerts.push({ id: 'unknown-spike', text: s.unknownSpike(dayLabel(unknownSpike.day, lang), f.num(unknownSpike.value)) })
  }

  return alerts
}

export default function DashboardAlerts({ data }: { data: TimeseriesData }) {
  const lang = useLang()
  const s = dashboardAlertsStrings(lang)
  const f = fmt(lang)

  const alerts = useMemo(() => deriveAlerts(data, s, f, lang), [data, s, f, lang])

  return (
    <div className="admin-card">
      <h3 className="font-semibold text-sm mb-3 text-primary flex items-center gap-2">
        <Icon name="warning" size={16} />
        {s.title}
      </h3>
      {alerts.length === 0 ? (
        <p className="text-sm text-muted py-4 text-center">{s.empty}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {alerts.map((a) => (
            <li
              key={a.id}
              className="text-xs text-secondary py-1 pr-2"
              style={{ borderRight: '3px solid var(--warning)' }}
            >
              {a.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
