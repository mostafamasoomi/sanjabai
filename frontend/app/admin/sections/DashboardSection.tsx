'use client'

import dynamic from 'next/dynamic'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/adminI18n'
import { StatCard, SectionHeader } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { useAdminResource } from '../useAdminResource'
import type { Analytics } from '../types'
import { dashboardStrings } from './DashboardSection.strings'

const AdminCharts = dynamic(() => import('../components/AdminCharts'), { ssr: false })

/* ═══════════════════════════════════════════════════════════════════════════
   Dashboard — GET /admin/analytics, fetched here rather than handed down
   from AdminPanel's old loadAll(). A failed load now says so instead of
   sitting on the skeleton forever.

   Money is integer toman and renders through f.price; counts through f.num.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function DashboardSection() {
  const lang = useLang()
  const s = dashboardStrings(lang)
  const f = fmt(lang)

  const { data: analytics, error, loading, reload } = useAdminResource<Analytics>(
    '/api/admin/analytics',
    (raw) => raw as Analytics,
    s.loadError,
  )

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title={s.title} subtitle={s.subtitle} />
        <RefreshButton onClick={reload} busy={loading} />
      </div>

      {error && <ErrorCard message={error} onRetry={reload} />}

      {!error && !analytics && <CardSkeleton count={5} />}

      {analytics && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
            <StatCard icon="profile" label={s.totalUsers} value={f.num(analytics.user_count)} color="var(--accent)" />
            <StatCard icon="check" label={s.activeUsers} value={f.num(analytics.active_users)} color="var(--positive)" />
            {/* f.price already carries the unit word — the label must not
                repeat it, and nothing here scales the raw toman figure. */}
            <StatCard icon="payment" label={s.totalRevenue} value={f.price(analytics.total_revenue, { fallback: s.zeroPrice })} color="var(--info)" />
            <StatCard icon="code" label={s.tokensUsed} value={f.num(analytics.total_tokens, { fallback: s.zeroCount })} color="var(--warning)" />
            <StatCard icon="chat" label={s.conversations} value={f.num(analytics.conv_count, { fallback: s.zeroCount })} color="var(--accent)" />
          </div>

          {/* Charts */}
          <AdminCharts />

          <div className="admin-card">
            <div className="flex items-center gap-2 mb-4">
              <Icon name="history" size={18} className="text-secondary" />
              <h3 className="font-semibold text-sm text-primary">{s.recentTransactions}</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-3">{s.colUserId}</th>
                    <th className="text-right p-3">{s.colAmount}</th>
                    <th className="text-right p-3">{s.colDescription}</th>
                    <th className="text-right p-3">{s.colDate}</th>
                  </tr>
                </thead>
                <tbody>
                  {(analytics.recent_ledger || []).length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-6 text-center text-sm text-muted">
                        {s.noTransactions}
                      </td>
                    </tr>
                  ) : (
                    (analytics.recent_ledger || []).map((l) => (
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
          </div>
        </>
      )}
    </div>
  )
}
