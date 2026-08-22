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

   Self-contained (fetches its own data via the `api` helper AdminPanel
   exposes), same pattern as ./MarkupSection.tsx. recharts is BANNED (see
   ../components/AdminCharts.tsx) -- the timeseries chart below is
   hand-written inline <svg>, following the exact pattern already used for
   the admin monitoring tab's latency chart
   (../components/MonitoringCharts.tsx::LatencyChart): a single polyline
   built from min/max-normalized points inside a fixed viewBox, no chart
   library involved.

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

/** Builds an SVG polyline `points` string from a series of non-negative amounts. */
function buildPoints(values: number[]): string {
  if (values.length === 0) return ''
  const max = Math.max(...values, 1)
  const stepX = values.length > 1 ? SVG_W / (values.length - 1) : 0
  return values
    .map((v, i) => {
      const x = values.length > 1 ? i * stepX : SVG_W / 2
      const y = SVG_H - (v / max) * (SVG_H - 8) - 4
      return `${x},${y}`
    })
    .join(' ')
}

function RevenueTrendChart({ days }: { days: DailyAmount[] }) {
  if (!days || days.length === 0) {
    return <div className="text-center text-sm text-muted py-8">داده‌ای برای رسم نمودار ثبت نشده است</div>
  }
  const values = days.map((d) => d.amount)
  const points = buildPoints(values)
  const total = values.reduce((a, b) => a + b, 0)

  return (
    <div>
      <p className="text-xs text-muted mb-3">
        مجموع {faNum(days.length)} روز اخیر: {faPrice(total)} — این مقدار بر اساس رویدادهای مصرف
        (usage_events) محاسبه می‌شود، نه پرداخت تکمیل‌شدهٔ درگاه؛ برای درآمد واقعی به کارت «درآمد واقعی» در بالا نگاه کنید.
      </p>
      <div dir="ltr">
        <svg
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          preserveAspectRatio="none"
          style={{ width: '100%', height: '140px', display: 'block' }}
        >
          <polyline
            points={points}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
      <div className="flex justify-between mt-2">
        <span className="text-[10px] text-muted">{dayLabel(days[0].day)}</span>
        <span className="text-[10px] text-muted">{dayLabel(days[days.length - 1].day)}</span>
      </div>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="admin-card flex items-center justify-between gap-4 flex-wrap" style={{ borderRight: '3px solid var(--danger)' }}>
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
  const [dailyRevenue, setDailyRevenue] = useState<DailyAmount[] | null>(null)
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
      const seriesBody: { daily_revenue?: DailyAmount[] } = await seriesRes.json()
      setStats(statsBody)
      setDailyRevenue(seriesBody.daily_revenue ?? [])
    } catch {
      // Deliberately no fallback to zero/empty here -- a failed fetch must
      // render as an error, never as a stat card silently showing ۰.
      setError('دریافت اطلاعات تحلیلی ناموفق بود')
      setStats(null)
      setDailyRevenue(null)
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
            <RevenueTrendChart days={dailyRevenue ?? []} />
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
