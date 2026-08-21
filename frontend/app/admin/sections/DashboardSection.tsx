'use client'

import dynamic from 'next/dynamic'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { StatCard } from './shared'
import type { Analytics } from '../AdminPanel'

const AdminCharts = dynamic(() => import('../components/AdminCharts'), { ssr: false })

/* ═══════════════════════════════════════════════════════════════════════════
   Dashboard — moved verbatim out of AdminPanel.tsx (page === 'dashboard').
   ═══════════════════════════════════════════════════════════════════════════ */

export default function DashboardSection({ analytics }: { analytics: Analytics | null }) {
  return (
    <div className="space-y-6">
      {analytics ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
            <StatCard icon="profile" label="کل کاربران" value={faNum(analytics.user_count)} color="var(--accent)" />
            <StatCard icon="check" label="کاربران فعال" value={faNum(analytics.active_users)} color="var(--positive)" />
            <StatCard icon="payment" label="درآمد کل (تومان)" value={faNum(analytics.total_revenue, { fallback: '۰' })} color="var(--info)" />
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
                    (analytics.recent_ledger || []).map((l: any) => (
                      <tr key={l.id}>
                        <td className="p-3 text-xs font-mono">{l.user_id}</td>
                        <td className="p-3">
                          <span className={l.amount > 0 ? 'badge badge-positive' : 'badge badge-danger'}>
                            {l.amount > 0 ? '+' : ''}{faNum(l.amount)}
                          </span>
                        </td>
                        <td className="p-3 text-xs text-secondary">{l.reason}</td>
                        <td className="p-3 text-xs text-muted">
                          {new Date(l.created_at).toLocaleDateString('fa-IR')}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="admin-card">
              <div className="skeleton h-3 w-20 mb-3 rounded" />
              <div className="skeleton h-7 w-16 rounded" />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
