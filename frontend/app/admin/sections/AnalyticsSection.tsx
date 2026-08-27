'use client'

import { useCallback, useEffect, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader, StatCard } from './shared'
import { analyticsStrings } from './AnalyticsSection.strings'
import AnalyticsCharts, { type TimeseriesData } from '../components/AnalyticsCharts'
import WindowSelector, { type ChartWindow } from '../components/charts/WindowSelector'

/* ═══════════════════════════════════════════════════════════════════════════
   Analytics — the shell around the full analysis surface:

     GET /admin/stats                        → all-time cards (kept: the
         total_revenue / total_admin_credit split exists because the panel
         once reported ten million toman of "revenue" from a single
         hand-seeded admin credit; two visibly different cards keep real
         money and seeded money apart)
     GET /admin/analytics/timeseries?days=   → WindowSelector + the charts,
         KPIs and tables in ../components/AnalyticsCharts.tsx
     GET /admin/export/{ledger,users}        → CSV downloads

   The section owns the `days` window and refetches on change; the chart
   surface is presentational. The margin/coverage honesty rules (null margin
   renders as «اندازه‌گیری‌نشده», partial coverage is announced, nothing is
   called net profit) are documented and enforced in AnalyticsCharts.tsx.

   The chart this section used to draw inline had its x-axis label row
   OUTSIDE the `dir="ltr"` wrapper, so the RTL panel mirrored the labels
   against the plot (oldest day labeled right, drawn left). The kit's
   LineChart/BarChart keep the labels inside the LTR wrapper — the rewrite
   must not and does not reintroduce that bug.

   A failed fetch renders as an explicit error with a retry button, never as
   an empty chart or a silent zero — a zero that actually means "the query
   failed" is exactly the class of lie this page exists to kill.
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

interface AnalyticsSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

async function downloadCsv(
  api: AnalyticsSectionProps['api'],
  path: string,
  filename: string,
  onDone: () => void,
  downloadErrorMsg: string,
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
    toast(downloadErrorMsg, 'error')
  } finally {
    onDone()
  }
}

function ErrorState({ message, onRetry, retryLabel }: { message: string; onRetry: () => void; retryLabel: string }) {
  return (
    <div className="admin-card admin-row justify-between gap-4" style={{ borderRight: '3px solid var(--danger)' }}>
      <div className="flex items-center gap-3">
        <Icon name="warning" size={20} style={{ color: 'var(--danger)' }} />
        <span className="text-sm text-primary">{message}</span>
      </div>
      <button className="btn btn-sm" onClick={onRetry}>
        <Icon name="refresh" size={14} />
        <span>{retryLabel}</span>
      </button>
    </div>
  )
}

export default function AnalyticsSection({ api }: AnalyticsSectionProps) {
  const lang = useLang()
  const s = analyticsStrings(lang)
  const f = fmt(lang)

  const [days, setDays] = useState<ChartWindow>(30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [series, setSeries] = useState<TimeseriesData | null>(null)
  const [exportingLedger, setExportingLedger] = useState(false)
  const [exportingUsers, setExportingUsers] = useState(false)

  const load = useCallback(async (window: ChartWindow) => {
    setLoading(true)
    setError(null)
    try {
      const [statsRes, seriesRes] = await Promise.all([
        api('/api/admin/stats'),
        api(`/api/admin/analytics/timeseries?days=${window}`),
      ])
      setStats((await statsRes.json()) as AdminStats)
      setSeries((await seriesRes.json()) as TimeseriesData)
    } catch {
      // Deliberately no fallback to zero/empty here — a failed fetch must
      // render as an error, never as a stat card silently showing ۰.
      setError(s.loadError)
      setStats(null)
      setSeries(null)
    } finally {
      setLoading(false)
    }
  }, [api, s.loadError])

  useEffect(() => {
    load(days)
  }, [load, days])

  return (
    <div className="space-y-6">
      <SectionHeader title={s.title} subtitle={s.subtitle} />

      {error && <ErrorState message={error} onRetry={() => load(days)} retryLabel={s.retry} />}

      {loading && !series && !error && (
        <div className="admin-card text-center text-sm text-muted py-8">{s.loading}</div>
      )}

      {!error && stats && series && (
        <>
          <h2 className="font-semibold text-sm text-primary">{s.allTimeTitle}</h2>
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <StatCard icon="payment" label={s.totalRevenue} value={f.price(stats.total_revenue)} color="var(--positive)" />
            <StatCard icon="gift" label={s.totalAdminCredit} value={f.price(stats.total_admin_credit)} color="var(--warning)" />
            <StatCard icon="user" label={s.totalUsers} value={f.num(stats.total_users)} color="var(--accent)" />
            <StatCard icon="chat" label={s.totalConversations} value={f.num(stats.total_conversations)} color="var(--accent)" />
          </div>

          {/* The selected window drives everything below it; the selector is
              disabled while a refetch is in flight so the data on screen and
              the pressed segment cannot disagree for long. */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <h2 className="font-semibold text-sm text-primary flex items-center gap-2">
              <Icon name="chart" size={16} />
              {s.trendTitle}
            </h2>
            <WindowSelector value={days} onChange={setDays} disabled={loading} />
          </div>

          <AnalyticsCharts data={series} />

          <div className="admin-card">
            <h3 className="font-semibold text-sm mb-1 text-primary">{s.exportTitle}</h3>
            <p className="text-xs text-muted mb-4">{s.exportSubtitle}</p>
            <div className="flex gap-3 flex-wrap">
              <button
                className="btn btn-sm"
                disabled={exportingLedger}
                onClick={() => {
                  setExportingLedger(true)
                  downloadCsv(api, '/api/admin/export/ledger', 'ledger_export.csv', () => setExportingLedger(false), s.downloadError)
                }}
              >
                {exportingLedger ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (
                  <Icon name="file" size={14} />
                )}
                <span>{s.exportLedger}</span>
              </button>
              <button
                className="btn btn-sm"
                disabled={exportingUsers}
                onClick={() => {
                  setExportingUsers(true)
                  downloadCsv(api, '/api/admin/export/users', 'users_export.csv', () => setExportingUsers(false), s.downloadError)
                }}
              >
                {exportingUsers ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (
                  <Icon name="file" size={14} />
                )}
                <span>{s.exportUsers}</span>
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
