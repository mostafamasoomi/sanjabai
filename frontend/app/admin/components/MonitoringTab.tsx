'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Icon } from '@/components/ui/Icon'
import { faNum, faPercent, faPrice, faTime } from '@/lib/format'
import { TrafficBars, LatencyChart, VolumeBars } from './MonitoringCharts'
import type { TrafficHour, VolumeDay } from './MonitoringCharts'

/* ═══════════════════════════════════════════════════════════════════════════
   Monitoring tab — read-only operator dashboard over GET /admin/monitoring.

   Every section can fail independently server-side (an `error: true` flag
   with empty data, never a 500) — this component mirrors that: each card
   renders what it has and shows a small error chip for what it doesn't,
   rather than letting one broken sub-query blank the whole page.

   List-shaped sections (`upstreams`, `models`) have nowhere to put an inline
   flag, so the server names them in a top-level `errors` array instead; the
   `sectionFailed()` helper below reads it. Without that, a failed query is
   served as `[]` and reads on screen as "there is nothing here".
   ═══════════════════════════════════════════════════════════════════════════ */

type ModelStatus = 'healthy' | 'degraded' | 'down' | 'unknown'

interface UpstreamRow {
  name: string
  alive: boolean
  latencyMs: number | null
  error: string | null
  modelStatusCounts: Partial<Record<ModelStatus, number>>
}

interface ModelRow {
  id: string
  displayName: string
  status: ModelStatus
  successRate: number | null
  latencyP50Ms: number | null
  latencyP95Ms: number | null
  sampleCount: number
  lastOkAt: string | null
  lastError: string | null
  checkedAt: string | null
}

interface ShortfallRow {
  userId: number
  model: string
  chargedAmount: number
  listedCost: string | null
  shortfall: string | null
  createdAt: string
}

interface EstimatedRow {
  userId: number
  model: string
  chargedAmount: number
  createdAt: string
}

interface NegativeBalanceRow { userId: number; balance: number }
interface LedgerMismatchRow { userId: number; walletBalance: number; ledgerBalance: number; delta: number }

interface MonitoringData {
  upstreams: UpstreamRow[]
  models: ModelRow[]
  traffic: { hours: TrafficHour[]; error?: boolean }
  volume: { days: VolumeDay[]; error?: boolean }
  billing: {
    shortfall: { count: number; sum: number; recent: ShortfallRow[]; error?: boolean }
    estimated: { count24h: number; count30d: number; recent: EstimatedRow[]; error?: boolean }
  }
  wallet: {
    negativeBalances: NegativeBalanceRow[]
    ledgerMismatches: LedgerMismatchRow[]
    negativeBalancesError?: boolean
    ledgerMismatchesError?: boolean
  }
  kuma: { monitoringUp: boolean; stale: boolean; source: 'cache' | 'last_good' | null; failing?: boolean; error?: boolean }
  /** Section keys the server could not produce. List-shaped sections
      (`upstreams`, `models`) have nowhere to put an inline `error` flag, so
      they degrade to `[]` — identical to "nothing configured". This names
      them, so an empty panel is never silently read as "no data". */
  errors?: string[]
  generatedAt: string
}

const POLL_MS = 60_000

const STATUS_FA: Record<ModelStatus, string> = { healthy: 'سالم', degraded: 'کاهش‌یافته', down: 'قطع', unknown: 'نامشخص' }
const STATUS_BADGE: Record<ModelStatus, string> = { healthy: 'badge-positive', degraded: 'badge-warning', down: 'badge-danger', unknown: 'badge-accent' }
const STATUS_ORDER: Record<ModelStatus, number> = { down: 0, degraded: 1, unknown: 2, healthy: 3 }

function ErrorChip() {
  return <span className="badge badge-danger" style={{ fontSize: '0.68rem' }}>خطا در این بخش</span>
}

function SectionTitle({ children, error }: { children: React.ReactNode; error?: boolean }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h3 className="font-semibold text-sm text-primary">{children}</h3>
      {error && <ErrorChip />}
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'positive' | 'warning' | 'danger' }) {
  const color = tone ? `var(--${tone})` : 'var(--accent)'
  return (
    <div className="admin-card" style={{ gap: '0.4rem' }}>
      <span className="text-xs text-muted">{label}</span>
      <span className="text-lg font-semibold" style={{ color }}>{value}</span>
    </div>
  )
}

function num(v: string | null): number | null {
  if (v == null) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

export default function MonitoringTab({ api }: { api: (path: string, opts?: RequestInit) => Promise<Response> }) {
  const [data, setData] = useState<MonitoringData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const r = await api('/api/admin/monitoring')
      const d = await r.json()
      setData(d)
    } catch {
      setError('خطا در بارگذاری اطلاعات پایش')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    pollRef.current = setInterval(() => load(true), POLL_MS)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [load])

  const sortedModels = useMemo(() => {
    if (!data) return []
    return [...data.models].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status])
  }, [data])

  const kpis = useMemo(() => {
    if (!data) return null
    const aliveCount = data.upstreams.filter((u) => u.alive).length
    const downModels = data.models.filter((m) => m.status === 'down').length
    let errors = 0, total = 0
    for (const h of data.traffic.hours) { errors += h.errors; total += h.total }
    const errorRate = total > 0 ? errors / total : null
    return { aliveCount, upstreamCount: data.upstreams.length, downModels, errorRate }
  }, [data])

  /** Did the server say it could not produce this section? Covers the
      list-shaped sections that cannot carry an inline `error` flag. */
  const sectionFailed = useCallback(
    (key: string) => Boolean(data?.errors?.includes(key)),
    [data],
  )

  return (
    <div className="space-y-4">
      {/* ─── Header ─── */}
      <div className="admin-card">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h2 className="font-semibold text-primary">پایش سامانه</h2>
            <p className="text-xs text-muted">وضعیت زنده درگاه‌های بالادست، مدل‌ها، ترافیک و صورتحساب</p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => load()} disabled={loading}>
            <Icon name="refresh" size={14} />
            <span>بازخوانی</span>
          </button>
        </div>
      </div>

      {loading && !data ? (
        <div className="admin-card"><p className="text-center text-sm text-muted py-8">در حال بارگذاری...</p></div>
      ) : error && !data ? (
        <div className="admin-card">
          <p className="text-center text-sm text-danger py-4">{error}</p>
          <div className="flex justify-center">
            <button className="btn btn-sm" onClick={() => load()}>تلاش مجدد</button>
          </div>
        </div>
      ) : data && kpis ? (
        <>
          {/* ─── KPI row ─── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Kpi
              label="درگاه‌های بالادست فعال"
              value={<span dir="ltr">{faNum(kpis.aliveCount)}/{faNum(kpis.upstreamCount)}</span>}
              tone={kpis.aliveCount === kpis.upstreamCount ? 'positive' : 'danger'}
            />
            <Kpi label="مدل‌های قطع" value={faNum(kpis.downModels)} tone={kpis.downModels > 0 ? 'danger' : 'positive'} />
            <Kpi
              label="پایش بیرونی (Kuma)"
              value={data.kuma.monitoringUp ? 'فعال' : 'قطع'}
              tone={!data.kuma.monitoringUp ? 'danger' : data.kuma.stale ? 'warning' : 'positive'}
            />
            <Kpi
              label="نرخ خطا (۲۴ ساعت)"
              value={faPercent(kpis.errorRate != null ? kpis.errorRate * 100 : null, 1)}
              tone={kpis.errorRate != null && kpis.errorRate > 0.05 ? 'danger' : 'positive'}
            />
          </div>

          {/* ─── Upstreams ─── */}
          <div className="admin-card">
            <SectionTitle error={sectionFailed('upstreams')}>درگاه‌های بالادست</SectionTitle>
            {data.upstreams.length === 0 ? (
              <p className="text-xs text-muted">موردی یافت نشد</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {data.upstreams.map((u) => (
                  <div key={u.name} className="admin-card" style={{ gap: '0.5rem' }}>
                    <div className="flex items-center justify-between">
                      <span dir="ltr" className="text-sm font-mono text-primary">{u.name}</span>
                      <span
                        title={u.alive ? 'زنده' : 'قطع'}
                        style={{
                          width: 9, height: 9, borderRadius: '50%',
                          background: u.alive ? 'var(--positive)' : 'var(--danger)',
                          display: 'inline-block', flexShrink: 0,
                        }}
                      />
                    </div>
                    <p className="text-xs text-muted">
                      تأخیر: {u.latencyMs != null ? <span dir="ltr">{faNum(u.latencyMs)} ms</span> : '—'}
                    </p>
                    {u.error && <p className="text-xs text-danger">{u.error}</p>}
                    <div className="flex flex-wrap gap-1.5">
                      {(Object.keys(STATUS_FA) as ModelStatus[]).map((s) => {
                        const n = u.modelStatusCounts[s]
                        if (!n) return null
                        return <span key={s} className={`badge ${STATUS_BADGE[s]}`}>{STATUS_FA[s]}: {faNum(n)}</span>
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ─── Models ─── */}
          <div className="admin-card overflow-x-auto">
            <SectionTitle error={sectionFailed('models')}>مدل‌ها</SectionTitle>
            {sortedModels.length === 0 ? (
              <p className="text-xs text-muted">موردی یافت نشد</p>
            ) : (
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-2">مدل</th>
                    <th className="text-right p-2">وضعیت</th>
                    <th className="text-right p-2">نرخ موفقیت</th>
                    <th className="text-right p-2">P50</th>
                    <th className="text-right p-2">P95</th>
                    <th className="text-right p-2">نمونه‌ها</th>
                    <th className="text-right p-2">آخرین وضعیت</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedModels.map((m) => {
                    const rate = m.successRate != null ? Math.min(100, Math.max(0, m.successRate * 100)) : null
                    return (
                      <tr key={m.id}>
                        <td className="p-2 text-xs">
                          <div className="text-primary">{m.displayName}</div>
                          <div className="font-mono text-muted" title={m.id}>{m.id}</div>
                        </td>
                        <td className="p-2"><span className={`badge ${STATUS_BADGE[m.status]}`}>{STATUS_FA[m.status]}</span></td>
                        <td className="p-2 text-xs">{faPercent(rate, 0)}</td>
                        <td className="p-2 text-xs">{m.latencyP50Ms != null ? <span dir="ltr">{faNum(m.latencyP50Ms)} ms</span> : '—'}</td>
                        <td className="p-2 text-xs">{m.latencyP95Ms != null ? <span dir="ltr">{faNum(m.latencyP95Ms)} ms</span> : '—'}</td>
                        <td className="p-2 text-xs">{faNum(m.sampleCount)}</td>
                        <td className="p-2 text-xs text-muted">
                          {m.lastError ? <span className="text-danger">{m.lastError}</span> : m.lastOkAt ? faTime(m.lastOkAt) : '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* ─── Traffic ─── */}
          <div className="admin-card">
            <SectionTitle error={data.traffic.error}>ترافیک (۲۴ ساعت اخیر)</SectionTitle>
            {data.traffic.hours.length === 0 ? (
              <p className="text-xs text-muted">داده‌ای موجود نیست</p>
            ) : (
              <div className="space-y-4">
                <TrafficBars hours={data.traffic.hours} />
                <LatencyChart hours={data.traffic.hours} />
              </div>
            )}
          </div>

          {/* ─── Volume ─── */}
          <div className="admin-card">
            <SectionTitle error={data.volume.error}>حجم (۷ روز اخیر)</SectionTitle>
            {data.volume.days.length === 0 ? (
              <p className="text-xs text-muted">داده‌ای موجود نیست</p>
            ) : (
              <VolumeBars days={data.volume.days} />
            )}
          </div>

          {/* ─── Billing: shortfall ─── */}
          <div className="admin-card overflow-x-auto">
            <SectionTitle error={data.billing.shortfall.error}>صورتحساب — کسری</SectionTitle>
            <div className="flex gap-4 mb-2">
              <span className="text-xs text-muted">تعداد: <span className="text-primary">{faNum(data.billing.shortfall.count)}</span></span>
              <span className="text-xs text-muted">مجموع کسری: <span className="text-danger">{faPrice(data.billing.shortfall.sum)}</span></span>
            </div>
            {data.billing.shortfall.recent.length === 0 ? (
              <p className="text-xs" style={{ color: 'var(--positive)' }}>موردی یافت نشد</p>
            ) : (
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-2">کاربر</th>
                    <th className="text-right p-2">مدل</th>
                    <th className="text-right p-2">مبلغ دریافتی</th>
                    <th className="text-right p-2">هزینه فهرست‌شده</th>
                    <th className="text-right p-2">کسری</th>
                    <th className="text-right p-2">زمان</th>
                  </tr>
                </thead>
                <tbody>
                  {data.billing.shortfall.recent.map((row, i) => (
                    <tr key={i}>
                      <td className="p-2 text-xs">{faNum(row.userId)}</td>
                      <td className="p-2 text-xs font-mono">{row.model}</td>
                      <td className="p-2 text-xs">{faPrice(row.chargedAmount)}</td>
                      <td className="p-2 text-xs">{faPrice(num(row.listedCost))}</td>
                      <td className="p-2 text-xs text-danger">{faPrice(num(row.shortfall))}</td>
                      <td className="p-2 text-xs text-muted">{faTime(row.createdAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* ─── Billing: estimated ─── */}
          <div className="admin-card overflow-x-auto">
            <SectionTitle error={data.billing.estimated.error}>صورتحساب — تخمینی</SectionTitle>
            <div className="flex gap-4 mb-2">
              <span className="text-xs text-muted">۲۴ ساعت اخیر: <span className="text-primary">{faNum(data.billing.estimated.count24h)}</span></span>
              <span className="text-xs text-muted">۳۰ روز اخیر: <span className="text-primary">{faNum(data.billing.estimated.count30d)}</span></span>
            </div>
            {data.billing.estimated.recent.length === 0 ? (
              <p className="text-xs" style={{ color: 'var(--positive)' }}>موردی یافت نشد</p>
            ) : (
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-2">کاربر</th>
                    <th className="text-right p-2">مدل</th>
                    <th className="text-right p-2">مبلغ دریافتی</th>
                    <th className="text-right p-2">زمان</th>
                  </tr>
                </thead>
                <tbody>
                  {data.billing.estimated.recent.map((row, i) => (
                    <tr key={i}>
                      <td className="p-2 text-xs">{faNum(row.userId)}</td>
                      <td className="p-2 text-xs font-mono">{row.model}</td>
                      <td className="p-2 text-xs">{faPrice(row.chargedAmount)}</td>
                      <td className="p-2 text-xs text-muted">{faTime(row.createdAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* ─── Wallet ─── */}
          <div className="admin-card overflow-x-auto">
            <SectionTitle error={data.wallet.negativeBalancesError}>کیف پول — موجودی منفی</SectionTitle>
            {data.wallet.negativeBalances.length === 0 ? (
              <p className="text-xs" style={{ color: 'var(--positive)' }}>موردی یافت نشد</p>
            ) : (
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-2">کاربر</th>
                    <th className="text-right p-2">موجودی</th>
                  </tr>
                </thead>
                <tbody>
                  {data.wallet.negativeBalances.map((row) => (
                    <tr key={row.userId}>
                      <td className="p-2 text-xs">{faNum(row.userId)}</td>
                      <td className="p-2 text-xs text-danger">{faPrice(row.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="admin-card overflow-x-auto">
            <SectionTitle error={data.wallet.ledgerMismatchesError}>کیف پول — ناهماهنگی دفتر کل</SectionTitle>
            {data.wallet.ledgerMismatches.length === 0 ? (
              <p className="text-xs" style={{ color: 'var(--positive)' }}>موردی یافت نشد</p>
            ) : (
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-2">کاربر</th>
                    <th className="text-right p-2">موجودی کیف پول</th>
                    <th className="text-right p-2">موجودی دفتر کل</th>
                    <th className="text-right p-2">اختلاف</th>
                  </tr>
                </thead>
                <tbody>
                  {data.wallet.ledgerMismatches.map((row) => (
                    <tr key={row.userId}>
                      <td className="p-2 text-xs">{faNum(row.userId)}</td>
                      <td className="p-2 text-xs">{faPrice(row.walletBalance)}</td>
                      <td className="p-2 text-xs">{faPrice(row.ledgerBalance)}</td>
                      <td className="p-2 text-xs text-danger">{faPrice(row.delta)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* ─── Kuma ─── */}
          <div className="admin-card" style={{ maxWidth: 420 }}>
            <SectionTitle error={sectionFailed('kuma') || data.kuma.error}>پایش بیرونی (Kuma)</SectionTitle>
            <div className="flex items-center gap-2">
              <span
                style={{
                  width: 9, height: 9, borderRadius: '50%',
                  background: data.kuma.monitoringUp ? 'var(--positive)' : 'var(--danger)',
                  display: 'inline-block', flexShrink: 0,
                }}
              />
              <span className="text-sm text-primary">{data.kuma.monitoringUp ? 'فعال' : 'قطع'}</span>
              {data.kuma.stale && <span className="badge badge-warning">داده قدیمی</span>}
            </div>
            <p className="text-xs text-muted">
              منبع: {data.kuma.source === 'cache' ? 'حافظه نهان' : data.kuma.source === 'last_good' ? 'آخرین وضعیت سالم' : '—'}
            </p>
            {data.kuma.failing && <p className="text-xs text-danger">هشدار: دریافت وضعیت از Kuma با خطا مواجه است</p>}
          </div>

          {/* ─── Footer ─── */}
          <p className="text-xs text-muted text-center">
            به‌روزرسانی: {faTime(data.generatedAt)} — این داده تا ۳۰ ثانیه در سرور کش می‌شود
          </p>
        </>
      ) : null}
    </div>
  )
}
