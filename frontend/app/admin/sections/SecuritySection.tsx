'use client'

import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faDate, toFaDigits } from '@/lib/format'
import { StatCard, SectionHeader } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { api, errMessage } from '../api'
import { useSecurityData, AUDIT_PAGE_SIZE } from '../useSecurityData'

/* ═══════════════════════════════════════════════════════════════════════════
   Security (SOC) — self-contained; the data, the polling and the pagination
   live in ../useSecurityData.ts.

   There is exactly one event feed on this screen: the admin audit log
   (GET /admin/audit-logs). The separate "رویدادهای امنیتی اخیر" table that
   used to sit above it is gone — no endpoint ever populated it, so it
   rendered a permanent "رویداد امنیتی ثبت نشده", which reads as "nothing
   suspicious has happened" when the truth was "nothing is being collected".
   A security screen that lies in the reassuring direction is worse than one
   panel short.

   Threat colours are inline hex rather than tokens on purpose: they must
   stay legible against both surfaces and must not shift with the theme's
   accent.
   ═══════════════════════════════════════════════════════════════════════════ */

const THREAT_COLOR = { low: '#22c55e', medium: '#eab308', high: '#f97316', critical: '#ef4444' } as const
const THREAT_LABEL = { low: 'پایین', medium: 'متوسط', high: 'بالا', critical: 'بحرانی' } as const

/* The backend matches `action LIKE '<filter>%'` — a PREFIX, not a substring
   (admin_analytics.py). Every action name it stores is dotted and namespaced
   (`admin.user.ban`, `auth.login_failed`, `api_key.revoke`), so the previous
   filters — `ban`, `unban`, `edit_user`, `create`, `delete`, `update` —
   could not match a single row, and clicking any of them emptied the table.
   These are real prefixes, taken from the actions the code actually writes.
   There is no `unban` action: POST /admin/users/{uid}/ban is a toggle and
   logs `admin.user.ban` in both directions. */
const AUDIT_FILTERS = [
  { label: 'همه', value: '' },
  { label: 'عملیات ادمین', value: 'admin.' },
  { label: 'کاربران', value: 'admin.user.' },
  { label: 'مدل‌ها', value: 'admin.model.' },
  { label: 'تعرفه‌ها', value: 'admin.pricing.' },
  { label: 'کلید API', value: 'api_key.' },
  { label: 'ورود و احراز هویت', value: 'auth.' },
]

export default function SecuritySection() {
  const {
    stats, statsError, logs, logsError, total, page, setPage,
    actionFilter, applyFilter, loading, reload,
  } = useSecurityData()

  // POST, not DELETE: /admin/users/{uid}/ban is a toggle and is the only
  // verb the backend defines. The old DELETE call 405'd every time, so this
  // button never actually unbanned anyone.
  const unbanUser = async (uid: number) => {
    try {
      await api(`/api/admin/users/${uid}/ban`, { method: 'POST' })
      toast('کاربر رفع مسدودیت شد', 'success')
      reload()
    } catch (err) {
      toast(errMessage(err, 'خطا در رفع مسدودیت'), 'error')
    }
  }

  const pageCount = Math.max(1, Math.ceil(total / AUDIT_PAGE_SIZE))
  const threatColor = stats ? THREAT_COLOR[stats.threat_level] ?? THREAT_COLOR.low : THREAT_COLOR.low

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader
          title="مرکز عملیات امنیتی (SOC)"
          subtitle="نظارت بر تهدیدات و عملیات ادمین"
        />
        <RefreshButton onClick={reload} busy={loading} />
      </div>

      {statsError && <ErrorCard message={statsError} onRetry={reload} />}
      {!statsError && !stats && <CardSkeleton count={4} />}

      {stats && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <div className="admin-card" style={{ borderRight: `3px solid ${threatColor}` }}>
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 rounded-lg" style={{ background: `${threatColor}15` }}>
                  <Icon name="warning" size={18} style={{ color: threatColor }} />
                </div>
                <span className="text-xs text-muted">سطح تهدید</span>
              </div>
              <p className="text-xl font-bold" style={{ color: threatColor }}>
                {THREAT_LABEL[stats.threat_level] ?? stats.threat_level}
              </p>
            </div>

            <StatCard icon="lock" label="ورودهای ناموفق (۲۴ ساعت)" value={faNum(stats.failed_logins_24h, { fallback: '۰' })} color="var(--danger)" />
            <StatCard icon="user" label="نشست‌های فعال" value={faNum(stats.active_sessions, { fallback: '۰' })} color="var(--info)" />
            <StatCard icon="security" label="کاربران مسدود شده" value={faNum(stats.banned_users?.length, { fallback: '۰' })} color="var(--warning)" />
          </div>

          {/* ─── Failed Login Chart (hand-rolled bars — no chart library) ─── */}
          <div className="admin-card">
            <div className="flex items-center gap-2 mb-4">
              <Icon name="chart" size={18} className="text-secondary" />
              <h3 className="font-semibold text-sm text-primary">
                نمودار ورودهای ناموفق (۲۴ ساعت اخیر)
              </h3>
            </div>
            <div className="flex items-end gap-1 h-24">
              {(stats.failed_login_chart || []).slice(-24).map((bar, i) => {
                const maxCount = Math.max(...(stats.failed_login_chart || []).map((b) => b.count), 1)
                const heightPct = (bar.count / maxCount) * 100
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className="w-full rounded-t transition-all duration-300"
                      style={{
                        height: `${Math.max(heightPct, 4)}%`,
                        background: bar.count > maxCount * 0.7
                          ? 'var(--danger)'
                          : bar.count > maxCount * 0.3
                            ? 'var(--warning)'
                            : 'var(--accent)',
                        opacity: 0.8,
                      }}
                      title={`${bar.hour}: ${faNum(bar.count)} تلاش ناموفق`}
                    />
                  </div>
                )
              })}
            </div>
            <div className="flex justify-between mt-2">
              <span className="text-[10px] text-muted">
                {stats.failed_login_chart?.[0]?.hour || ''}
              </span>
              <span className="text-[10px] text-muted">
                {stats.failed_login_chart?.[stats.failed_login_chart.length - 1]?.hour || ''}
              </span>
            </div>
          </div>

          {/* ─── Banned Users ──────────────────────────────────── */}
          <div className="admin-card">
            <div className="flex items-center gap-2 mb-4">
              <Icon name="security" size={18} className="text-warning" />
              <h3 className="font-semibold text-sm text-primary">کاربران مسدود شده</h3>
              <span className="badge badge-warning mr-auto">{faNum(stats.banned_users?.length, { fallback: '۰' })}</span>
            </div>
            {(stats.banned_users || []).length === 0 ? (
              <div className="text-center py-6 text-sm text-muted">
                کاربر مسدود شده‌ای وجود ندارد
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="admin-table w-full text-sm">
                  <thead>
                    <tr>
                      <th className="text-right p-3">شناسه</th>
                      <th className="text-right p-3">نام کاربری</th>
                      <th className="text-right p-3">ایمیل</th>
                      <th className="text-right p-3">تاریخ مسدودیت</th>
                      <th className="text-right p-3">عملیات</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(stats.banned_users || []).map((u) => (
                      <tr key={u.id}>
                        <td className="p-3 text-xs font-mono">{u.id}</td>
                        <td className="p-3 text-sm text-primary">{u.username || '—'}</td>
                        <td className="p-3 text-xs text-secondary">{u.email}</td>
                        <td className="p-3 text-xs text-muted">{faDate(u.banned_at)}</td>
                        <td className="p-3">
                          <button
                            className="btn btn-sm"
                            style={{ background: 'var(--positive)', color: 'var(--text-on-accent)' }}
                            onClick={() => unbanUser(u.id)}
                          >
                            رفع مسدودیت
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* ─── Audit Log Table — the one event feed on this screen ────── */}
      <div className="admin-card">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="history" size={18} className="text-accent" />
          <h3 className="font-semibold text-sm text-primary">لاگ عملیات ادمین</h3>
          {loading && (
            <span className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin inline-block" />
          )}
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          {AUDIT_FILTERS.map((f) => (
            <button
              key={f.value}
              className={`btn btn-sm ${actionFilter === f.value ? 'font-bold' : ''}`}
              style={{
                background: actionFilter === f.value ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                color: actionFilter === f.value ? 'var(--accent)' : 'var(--text-secondary)',
              }}
              onClick={() => applyFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>

        {logsError ? (
          <ErrorCard message={logsError} onRetry={reload} />
        ) : (
          <div className="overflow-x-auto">
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-right p-3">شناسه</th>
                  <th className="text-right p-3">عملیات</th>
                  <th className="text-right p-3">نوع هدف</th>
                  <th className="text-right p-3">شناسه هدف</th>
                  <th className="text-right p-3">جزئیات</th>
                  <th className="text-right p-3">زمان</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-sm text-muted">
                      لاگ عملیاتی ثبت نشده
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={log.id}>
                      <td className="p-3 text-xs font-mono">{log.id}</td>
                      <td className="p-3">
                        <span className={`badge ${
                          log.action?.includes('ban') ? 'badge-danger'
                          : log.action?.includes('delete') ? 'badge-warning'
                          : log.action?.includes('create') ? 'badge-positive'
                          : 'badge-accent'
                        }`}>
                          {log.action || '—'}
                        </span>
                      </td>
                      <td className="p-3 text-xs text-secondary">{log.target_type || '—'}</td>
                      <td className="p-3 text-xs font-mono">{log.target_id ?? '—'}</td>
                      <td className="p-3 text-xs text-secondary break-words max-w-md">{log.details || '—'}</td>
                      <td className="p-3 text-xs text-muted">
                        {toFaDigits(new Date(log.created_at).toLocaleString('fa-IR'))}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination — the buttons only move `page`; the fetch is derived
            from it in useSecurityData, so a click can no longer re-request
            the page it was already on. */}
        {!logsError && total > AUDIT_PAGE_SIZE && (
          <div className="flex items-center justify-between mt-4 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
            <span className="text-xs text-muted">
              صفحه {faNum(page)} از {faNum(pageCount)}
            </span>
            <div className="flex gap-2">
              <button className="btn btn-sm" disabled={page <= 1 || loading} onClick={() => setPage(Math.max(1, page - 1))}>
                قبلی
              </button>
              <button className="btn btn-sm" disabled={page >= pageCount || loading} onClick={() => setPage(page + 1)}>
                بعدی
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
