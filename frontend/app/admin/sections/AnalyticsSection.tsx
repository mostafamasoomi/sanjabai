'use client'

import { useCallback, useEffect, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice } from '@/lib/format'
import { SectionHeader, StatCard } from './shared'

/* ═══════════════════════════════════════════════════════════════════════════
   Analytics — wires up four admin endpoints that had zero frontend
   consumers before this (grepped): GET /admin/stats, GET
   /admin/analytics/timeseries, GET /admin/export/ledger, GET
   /admin/export/users.

   Why this exists: admin.py's `admin_stats`/`admin_analytics` used to
   report `total_revenue` as "SUM of every positive ledger row", which
   conflated real gateway payments with admin-seeded wallet credits,
   refunds and released reservations. On production this showed
   10,000,000 toman of "revenue" for a business that had taken zero
   payments -- the single positive ledger row was a hand-seeded admin
   credit. Both endpoints now return `total_revenue` (completed gateway
   payments only) AND `total_admin_credit` (everything else positive)
   separately -- see the long comment above the fixed queries in
   admin.py::admin_analytics. This section's whole point is to put those
   two numbers in front of the owner as two *visibly different* cards, so
   real money is never mistaken for seeded money again.

   The SAME naming mistake existed one endpoint over, in
   GET /admin/analytics/timeseries: it returned a `daily_revenue` series
   computed from `usage_events.charged_amount` -- consumption (what users
   were charged), not revenue. That endpoint now returns `daily_consumption`
   (renamed, same meaning) AND a new `daily_gateway_revenue` series resolved
   from completed `payments`/`payment_orders`, mirroring the total_revenue /
   total_admin_credit split above. Both old misleading keys
   (`daily_revenue`, `revenue_by_model`) are gone -- not kept as aliases --
   so this file reads `daily_consumption` / `daily_gateway_revenue` /
   `consumption_by_model` and renders both money series as two visibly
   different lines with honest labels, never one line implying it's revenue.

   Self-contained (fetches its own data via the `api` helper AdminPanel
   exposes), same pattern as ./MarkupSection.tsx. recharts is BANNED (see
   ../components/AdminCharts.tsx) -- the timeseries chart below is
   hand-written inline <svg>, following the exact pattern already used for
   the admin monitoring tab's latency chart
   (../components/MonitoringCharts.tsx::LatencyChart): polylines built from
   min/max-normalized points inside a fixed viewBox, no chart library
   involved.

   A failed fetch renders as an explicit error with a retry button, never
   as an empty chart or a silent zero -- a zero that actually means "the
   query failed" is exactly the class of lie this whole fix exists to kill.
   ═══════════════════════════════════════════════════════════════════════════ */

interface AdminStats {
  total_users: number
  active_users: number
  total_conversations: number
  total_api_keys: number
  total_revenue: number
  total_admin_credit: number
  total_usage_events: number
  total_models: number
}

interface DailyAmount {
  day: string
  amount: number
}

interface AnalyticsSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

const SVG_W = 600
const SVG_H = 140

/** Short day label from a `YYYY-MM-DD` string, e.g. "۲۱ مرداد". */
function dayLabel(dateStr: string): string {
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  return d
    .toLocaleDateString('fa-IR', { month: 'short', day: 'numeric' })
    .replace(/[0-9]/g, (c) => '۰۱۲۳۴۵۶۷۸۹'[Number(c)])
}

/** Builds an SVG polyline `points` string, normalizing against a shared
 * (not per-series) max so two series drawn on the same axes stay comparable
 * -- a series near zero must visibly look near zero, not get rescaled to
 * fill the chart on its own. */
function buildSharedPoints(values: number[], sharedMax: number): string {
  if (values.length === 0) return ''
  const max = Math.max(sharedMax, 1)
  const stepX = values.length > 1 ? SVG_W / (values.length - 1) : 0
  return values
    .map((v, i) => {
      const x = values.length > 1 ? i * stepX : SVG_W / 2
      const y = SVG_H - (v / max) * (SVG_H - 8) - 4
      return `${x},${y}`
    })
    .join(' ')
}

/** Two-series honesty chart: consumption (spend on model usage) vs. real
 * gateway revenue (completed payments), drawn as two visibly different
 * polylines on the same axes so the gap between "what users were charged"
 * and "money that actually arrived" is never hidden behind a single line
 * that could be mistaken for revenue. */
function ConsumptionVsRevenueChart({
  consumption,
  gatewayRevenue,
}: {
  consumption: DailyAmount[]
  gatewayRevenue: DailyAmount[]
}) {
  if (!consumption || consumption.length === 0) {
    return <div className="text-center text-sm text-muted py-8">داده‌ای برای رسم نمودار ثبت نشده است</div>
  }
  const gatewayByDay = new Map(gatewayRevenue.map((d) => [d.day, d.amount]))
  const consumptionValues = consumption.map((d) => d.amount)
  const gatewayValues = consumption.map((d) => gatewayByDay.get(d.day) ?? 0)
  const sharedMax = Math.max(...consumptionValues, ...gatewayValues, 1)

  const consumptionPoints = buildSharedPoints(consumptionValues, sharedMax)
  const gatewayPoints = buildSharedPoints(gatewayValues, sharedMax)
  const consumptionTotal = consumptionValues.reduce((a, b) => a + b, 0)
  const gatewayTotal = gatewayValues.reduce((a, b) => a + b, 0)

  return (
    <div>
      <div className="flex flex-wrap items-center gap-4 mb-3">
        <span className="flex items-center gap-1 text-xs">
          <span style={{ width: 10, height: 10, borderRadius: 2, background: 'var(--accent)', display: 'inline-block' }} />
          مصرف کاربران (charged_amount) — مجموع {faPrice(consumptionTotal)}
        </span>
        <span className="flex items-center gap-1 text-xs">
          <span style={{ width: 10, height: 10, borderRadius: 2, background: 'var(--positive, #16a34a)', display: 'inline-block' }} />
          درآمد واقعی درگاه (پرداخت‌های تکمیل‌شده) — مجموع {faPrice(gatewayTotal)}
        </span>
      </div>
      <p className="text-xs text-muted mb-3">
        مصرف یعنی چه مبلغی بابت استفاده از مدل‌ها از کاربران کسر شده — نه لزوماً پولی که وارد درگاه شده. برای
        {faNum(consumption.length)} روز اخیر، این دو عدد آگاهانه جدا از هم رسم شده‌اند تا با هم اشتباه گرفته نشوند.
      </p>
      <div dir="ltr">
        <svg
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          preserveAspectRatio="none"
          style={{ width: '100%', height: '140px', display: 'block' }}
        >
          <polyline
            points={consumptionPoints}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
          <polyline
            points={gatewayPoints}
            fill="none"
            stroke="var(--positive, #16a34a)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
      <div className="flex justify-between mt-2">
        <span className="text-[10px] text-muted">{dayLabel(consumption[0].day)}</span>
        <span className="text-[10px] text-muted">{dayLabel(consumption[consumption.length - 1].day)}</span>
      </div>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="admin-card admin-row justify-between gap-4" style={{ borderRight: '3px solid var(--danger)' }}>
      <div className="flex items-center gap-3">
        <Icon name="warning" size={20} style={{ color: 'var(--danger)' }} />
        <span className="text-sm text-primary">{message}</span>
      </div>
      <button className="btn btn-sm" onClick={onRetry}>
        <Icon name="refresh" size={14} />
        <span>تلاش دوباره</span>
      </button>
    </div>
  )
}

async function downloadCsv(
  api: AnalyticsSectionProps['api'],
  path: string,
  filename: string,
  onDone: () => void,
) {
  try {
    const res = await api(path)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    toast('دریافت فایل خروجی ناموفق بود', 'error')
  } finally {
    onDone()
  }
}

export default function AnalyticsSection({ api }: AnalyticsSectionProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [dailyConsumption, setDailyConsumption] = useState<DailyAmount[] | null>(null)
  const [dailyGatewayRevenue, setDailyGatewayRevenue] = useState<DailyAmount[] | null>(null)
  const [exportingLedger, setExportingLedger] = useState(false)
  const [exportingUsers, setExportingUsers] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [statsRes, seriesRes] = await Promise.all([
        api('/api/admin/stats'),
        api('/api/admin/analytics/timeseries'),
      ])
      const statsBody: AdminStats = await statsRes.json()
      const seriesBody: { daily_consumption?: DailyAmount[]; daily_gateway_revenue?: DailyAmount[] } =
        await seriesRes.json()
      setStats(statsBody)
      setDailyConsumption(seriesBody.daily_consumption ?? [])
      setDailyGatewayRevenue(seriesBody.daily_gateway_revenue ?? [])
    } catch {
      // Deliberately no fallback to zero/empty here -- a failed fetch must
      // render as an error, never as a stat card silently showing ۰.
      setError('دریافت اطلاعات تحلیلی ناموفق بود')
      setStats(null)
      setDailyConsumption(null)
      setDailyGatewayRevenue(null)
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-6">
      <SectionHeader
        title="تحلیل و درآمد"
        subtitle="درآمد واقعیِ واردشده از درگاه پرداخت، جدا از اعتبارهایی که ادمین دستی شارژ کرده — دو عدد، دو کارت، بدون قاطی‌شدن"
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {loading && !error && (
        <div className="admin-card text-center text-sm text-muted py-8">در حال بارگذاری…</div>
      )}

      {!loading && !error && stats && (
        <>
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <StatCard
              icon="payment"
              label="درآمد واقعی (پرداخت‌های تکمیل‌شدهٔ درگاه)"
              value={faPrice(stats.total_revenue)}
              color="var(--positive, #16a34a)"
            />
            <StatCard
              icon="gift"
              label="اعتبار دستی ادمین (غیر از درگاه)"
              value={faPrice(stats.total_admin_credit)}
              color="var(--warning, #d97706)"
            />
            <StatCard icon="user" label="تعداد کاربران" value={faNum(stats.total_users)} color="var(--accent)" />
            <StatCard icon="chat" label="تعداد گفتگوها" value={faNum(stats.total_conversations)} color="var(--accent)" />
          </div>

          <div className="admin-card">
            <h3 className="font-semibold text-sm mb-1 text-primary flex items-center gap-2">
              <Icon name="chart" size={16} />
              روند ۳۰ روز اخیر
            </h3>
            <ConsumptionVsRevenueChart consumption={dailyConsumption ?? []} gatewayRevenue={dailyGatewayRevenue ?? []} />
          </div>

          <div className="admin-card">
            <h3 className="font-semibold text-sm mb-1 text-primary">خروجی داده</h3>
            <p className="text-xs text-muted mb-4">دانلود کامل دفتر تراکنش‌ها (ledger) یا فهرست کاربران به صورت CSV</p>
            <div className="flex gap-3 flex-wrap">
              <button
                className="btn btn-sm"
                disabled={exportingLedger}
                onClick={() => {
                  setExportingLedger(true)
                  downloadCsv(api, '/api/admin/export/ledger', 'ledger_export.csv', () => setExportingLedger(false))
                }}
              >
                {exportingLedger ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (
                  <Icon name="file" size={14} />
                )}
                <span>خروجی دفتر تراکنش‌ها</span>
              </button>
              <button
                className="btn btn-sm"
                disabled={exportingUsers}
                onClick={() => {
                  setExportingUsers(true)
                  downloadCsv(api, '/api/admin/export/users', 'users_export.csv', () => setExportingUsers(false))
                }}
              >
                {exportingUsers ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (
                  <Icon name="file" size={14} />
                )}
                <span>خروجی کاربران</span>
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
