'use client'

import dynamic from 'next/dynamic'
import { Icon } from '@/components/ui/Icon'
import { faNum, faPrice, faDate } from '@/lib/format'
import { StatCard, SectionHeader } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { useAdminResource } from '../useAdminResource'
import type { Analytics } from '../types'

const AdminCharts = dynamic(() => import('../components/AdminCharts'), { ssr: false })

/* ═══════════════════════════════════════════════════════════════════════════
   Dashboard — GET /admin/analytics, fetched here rather than handed down
   from AdminPanel's old loadAll(). A failed load now says so instead of
   sitting on the skeleton forever.

   Money is integer toman and renders through faPrice; counts through faNum.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function DashboardSection() {
  const { data: analytics, error, loading, reload } = useAdminResource<Analytics>(
    '/api/admin/analytics',
    (raw) => raw as Analytics,
    'خطا در دریافت آمار داشبورد',
  )

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title="داشبورد" subtitle="نمای کلی کاربران، درآمد و مصرف" />
        <RefreshButton onClick={reload} busy={loading} />
      </div>

      {error && <ErrorCard message={error} onRetry={reload} />}

      {!error && !analytics && <CardSkeleton count={5} />}

      {analytics && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
            <StatCard icon="profile" label="کل کاربران" value={faNum(analytics.user_count)} color="var(--accent)" />
            <StatCard icon="check" label="کاربران فعال" value={faNum(analytics.active_users)} color="var(--positive)" />
            {/* faPrice already carries the «تومان» unit — the label must not
                repeat it, and nothing here scales the raw toman figure. */}
            <StatCard icon="payment" label="درآمد کل" value={faPrice(analytics.total_revenue, { fallback: '۰ تومان' })} color="var(--info)" />
            <StatCard icon="code" label="توکن مصرفی" value={faNum(analytics.total_tokens, { fallback: '۰' })} color="var(--warning)" />
            <StatCard icon="chat" label="گفتگوها" value={faNum(analytics.conv_count, { fallback: '۰' })} color="var(--accent)" />
          </div>

          {/* Charts */}
          <AdminCharts />

          <div className="admin-card">
            <div className="flex items-center gap-2 mb-4">
              <Icon name="history" size={18} className="text-secondary" />
              <h3 className="font-semibold text-sm text-primary">تراکنش‌های اخیر</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-3">شناسه کاربر</th>
                    <th className="text-right p-3">مبلغ</th>
                    <th className="text-right p-3">شرح</th>
                    <th className="text-right p-3">تاریخ</th>
                  </tr>
                </thead>
                <tbody>
                  {(analytics.recent_ledger || []).length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-6 text-center text-sm text-muted">
                        تراکنشی ثبت نشده
                      </td>
                    </tr>
                  ) : (
                    (analytics.recent_ledger || []).map((l) => (
                      <tr key={l.id}>
                        <td className="p-3 text-xs font-mono">{l.user_id}</td>
                        <td className="p-3">
                          <span className={l.amount > 0 ? 'badge badge-positive' : 'badge badge-danger'}>
                            {faPrice(l.amount, { signed: true })}
                          </span>
                        </td>
                        <td className="p-3 text-xs text-secondary">{l.reason}</td>
                        <td className="p-3 text-xs text-muted">{faDate(l.created_at)}</td>
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
