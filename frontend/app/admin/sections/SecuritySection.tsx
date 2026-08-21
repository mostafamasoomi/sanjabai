'use client'

import { Icon } from '@/components/ui/Icon'
import { faNum, toFaDigits } from '@/lib/format'
import { StatCard, SectionHeader } from './shared'
import type { SecurityStats, SecurityEvent, AuditLog } from '../AdminPanel'

/* ═══════════════════════════════════════════════════════════════════════════
   Security (SOC) — moved verbatim out of AdminPanel.tsx (page === 'security').
   All state, the polling effects, and the handlers still live in AdminPanel
   (the generic "refresh" button in the shared page header calls
   loadSecurityData specifically when page === 'security', so that state and
   its refresh function must stay put); this component is purely
   presentational.
   ═══════════════════════════════════════════════════════════════════════════ */

interface SecuritySectionProps {
  securityStats: SecurityStats | null
  securityEvents: SecurityEvent[]
  auditLogs: AuditLog[]
  auditPage: number
  setAuditPage: (p: number) => void
  auditTotal: number
  auditActionFilter: string
  securityLoading: boolean
  unbanUser: (uid: number) => void
  loadAuditWithFilter: (action: string) => void
  loadSecurityData: () => void
}

export default function SecuritySection({
  securityStats, securityEvents, auditLogs, auditPage, setAuditPage, auditTotal,
  auditActionFilter, securityLoading, unbanUser, loadAuditWithFilter, loadSecurityData,
}: SecuritySectionProps) {
  return (
    <div className="space-y-6">
      <SectionHeader
        title="مرکز عملیات امنیتی (SOC)"
        subtitle="نظارت بر تهدیدات، رویدادها و فعالیت کاربران"
      />

      {/* ─── Threat Level + Stats Row ──────────────────────────── */}
      {securityStats ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            {/* Threat Level Card */}
            <div
              className="admin-card"
              style={{
                borderRight: `3px solid ${
                  securityStats.threat_level === 'critical' ? '#ef4444'
                  : securityStats.threat_level === 'high' ? '#f97316'
                  : securityStats.threat_level === 'medium' ? '#eab308'
                  : '#22c55e'
                }`,
              }}
            >
              <div className="flex items-center gap-3 mb-3">
                <div
                  className="p-2 rounded-lg"
                  style={{
                    background: `${
                      securityStats.threat_level === 'critical' ? '#ef4444'
                      : securityStats.threat_level === 'high' ? '#f97316'
                      : securityStats.threat_level === 'medium' ? '#eab308'
                      : '#22c55e'
                    }15`,
                  }}
                >
                  <Icon
                    name="warning"
                    size={18}
                    style={{
                      color: securityStats.threat_level === 'critical' ? '#ef4444'
                        : securityStats.threat_level === 'high' ? '#f97316'
                        : securityStats.threat_level === 'medium' ? '#eab308'
                        : '#22c55e',
                    }}
                  />
                </div>
                <span className="text-xs text-muted">سطح تهدید</span>
              </div>
              <p
                className="text-xl font-bold"
                style={{
                  color: securityStats.threat_level === 'critical' ? '#ef4444'
                    : securityStats.threat_level === 'high' ? '#f97316'
                    : securityStats.threat_level === 'medium' ? '#eab308'
                    : '#22c55e',
                }}
              >
                {{ low: 'پایین', medium: 'متوسط', high: 'بالا', critical: 'بحرانی' }[securityStats.threat_level]}
              </p>
            </div>

            <StatCard
              icon="lock"
              label="ورودهای ناموفق (۲۴ ساعت)"
              value={faNum(securityStats.failed_logins_24h)}
              color="var(--danger)"
            />
            <StatCard
              icon="user"
              label="نشستهای فعال"
              value={faNum(securityStats.active_sessions)}
              color="var(--info)"
            />
            <StatCard
              icon="security"
              label="کاربران مسدود شده"
              value={faNum(securityStats.banned_users?.length, { fallback: '۰' })}
              color="var(--warning)"
            />
          </div>

          {/* ─── Failed Login Chart (sparkline-style bars) ──────── */}
          <div className="admin-card">
            <div className="flex items-center gap-2 mb-4">
              <Icon name="chart" size={18} className="text-secondary" />
              <h3 className="font-semibold text-sm text-primary">
                نمودار ورودهای ناموفق (۲۴ ساعت اخیر)
              </h3>
            </div>
            <div className="flex items-end gap-1 h-24">
              {(securityStats.failed_login_chart || []).slice(-24).map((bar, i) => {
                const maxCount = Math.max(...(securityStats.failed_login_chart || []).map((b) => b.count), 1)
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
                      title={`${bar.hour}: ${bar.count} تلاش ناموفق`}
                    />
                  </div>
                )
              })}
            </div>
            <div className="flex justify-between mt-2">
              <span className="text-[10px] text-muted">
                {securityStats.failed_login_chart?.[0]?.hour || ''}
              </span>
              <span className="text-[10px] text-muted">
                {securityStats.failed_login_chart?.[securityStats.failed_login_chart.length - 1]?.hour || ''}
              </span>
            </div>
          </div>

          {/* ─── Banned Users ──────────────────────────────────── */}
          <div className="admin-card">
            <div className="flex items-center gap-2 mb-4">
              <Icon name="security" size={18} className="text-warning" />
              <h3 className="font-semibold text-sm text-primary">
                کاربران مسدود شده
              </h3>
              <span className="badge badge-warning mr-auto">{securityStats.banned_users?.length || 0}</span>
            </div>
            {(securityStats.banned_users || []).length === 0 ? (
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
                    {(securityStats.banned_users || []).map((u) => (
                      <tr key={u.id}>
                        <td className="p-3 text-xs font-mono">{u.id}</td>
                        <td className="p-3 text-sm text-primary">{u.username || '—'}</td>
                        <td className="p-3 text-xs text-secondary">{u.email}</td>
                        <td className="p-3 text-xs text-muted">
                          {u.banned_at ? new Date(u.banned_at).toLocaleDateString('fa-IR') : '—'}
                        </td>
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
      ) : (
        /* Loading skeleton */
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="admin-card">
              <div className="skeleton h-3 w-20 mb-3 rounded" />
              <div className="skeleton h-7 w-16 rounded" />
            </div>
          ))}
        </div>
      )}

      {/* ─── Security Events Table ──────────────────────────── */}
      <div className="admin-card">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="notification" size={18} className="text-danger" />
          <h3 className="font-semibold text-sm text-primary">
            رویدادهای امنیتی اخیر
          </h3>
          {securityLoading && (
            <span className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin inline-block" />
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-3">نوع رویداد</th>
                <th className="text-right p-3">کاربر</th>
                <th className="text-right p-3">آدرس IP</th>
                <th className="text-right p-3">جزئیات</th>
                <th className="text-right p-3">زمان</th>
              </tr>
            </thead>
            <tbody>
              {securityEvents.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-sm text-muted">
                    رویداد امنیتی ثبت نشده
                  </td>
                </tr>
              ) : (
                securityEvents.map((ev) => (
                  <tr key={ev.id}>
                    <td className="p-3">
                      <span className={`badge ${
                        ev.event_type?.includes('failed') || ev.event_type?.includes('lockout')
                          ? 'badge-danger'
                          : ev.event_type?.includes('login') || ev.event_type?.includes('success')
                            ? 'badge-positive'
                            : 'badge-accent'
                      }`}>
                        {ev.event_type || 'نامشخص'}
                      </span>
                    </td>
                    <td className="p-3 text-xs text-secondary">
                      {ev.user_email || ev.user_id || '—'}
                    </td>
                    <td className="p-3 text-xs font-mono text-muted">
                      {ev.ip_address || '—'}
                    </td>
                    <td className="p-3 text-xs text-secondary">
                      {ev.details || '—'}
                    </td>
                    <td className="p-3 text-xs text-muted">
                      {toFaDigits(new Date(ev.created_at).toLocaleString('fa-IR'))}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── Audit Log Table ─────────────────────────────────── */}
      <div className="admin-card">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="history" size={18} className="text-accent" />
          <h3 className="font-semibold text-sm text-primary">
            لاگ عملیات ادمین
          </h3>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap gap-2 mb-4">
          {[
            { label: 'همه', value: '' },
            { label: 'ban', value: 'ban' },
            { label: 'unban', value: 'unban' },
            { label: 'edit_user', value: 'edit_user' },
            { label: 'create', value: 'create' },
            { label: 'delete', value: 'delete' },
            { label: 'update', value: 'update' },
          ].map((f) => (
            <button
              key={f.value}
              className={`btn btn-sm ${auditActionFilter === f.value ? 'font-bold' : ''}`}
              style={{
                background: auditActionFilter === f.value ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                color: auditActionFilter === f.value ? 'var(--accent)' : 'var(--text-secondary)',
              }}
              onClick={() => loadAuditWithFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>

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
              {auditLogs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-sm text-muted">
                    لاگ عملیاتی ثبت نشده
                  </td>
                </tr>
              ) : (
                auditLogs.map((log) => (
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
                    <td className="p-3 text-xs text-secondary">
                      {log.target_type || '—'}
                    </td>
                    <td className="p-3 text-xs font-mono">
                      {log.target_id || '—'}
                    </td>
                    <td className="p-3 text-xs text-secondary">
                      {log.details || '—'}
                    </td>
                    <td className="p-3 text-xs text-muted">
                      {toFaDigits(new Date(log.created_at).toLocaleString('fa-IR'))}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {auditTotal > 50 && (
          <div className="flex items-center justify-between mt-4 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
            <span className="text-xs text-muted">
              صفحه {auditPage} از {Math.ceil(auditTotal / 50)}
            </span>
            <div className="flex gap-2">
              <button
                className="btn btn-sm"
                disabled={auditPage <= 1}
                onClick={() => { setAuditPage(Math.max(1, auditPage - 1)); loadSecurityData() }}
              >
                قبلی
              </button>
              <button
                className="btn btn-sm"
                disabled={auditPage >= Math.ceil(auditTotal / 50)}
                onClick={() => { setAuditPage(auditPage + 1); loadSecurityData() }}
              >
                بعدی
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
