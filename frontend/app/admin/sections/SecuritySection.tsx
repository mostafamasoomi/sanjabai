'use client'

import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { formatAuditDetails } from '@/lib/auditDetails'
import { StatCard, SectionHeader } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { api, errMessage } from '../api'
import { useSecurityData, AUDIT_PAGE_SIZE } from '../useSecurityData'
import { securitySectionStrings } from './SecuritySection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Security (SOC) — self-contained; the data, the polling and the pagination
   live in ../useSecurityData.ts.

   There is exactly one event feed on this screen: the admin audit log
   (GET /admin/audit-logs). The separate "recent security events" table that
   used to sit above it is gone — no endpoint ever populated it, so it
   rendered a permanent "no security event recorded", which reads as
   "nothing suspicious has happened" when the truth was "nothing is being
   collected". A security screen that lies in the reassuring direction is
   worse than one panel short.

   Threat colours are inline hex rather than tokens on purpose: they must
   stay legible against both surfaces and must not shift with the theme's
   accent.
   ═══════════════════════════════════════════════════════════════════════════ */

const THREAT_COLOR = { low: '#22c55e', medium: '#eab308', high: '#f97316', critical: '#ef4444' } as const

/* `audit_logs.details` is jsonb (confirmed via \d audit_logs), so the API
   can hand back a string, a number, a boolean, an array, a plain object, or
   null -- `AuditLog['details']` is typed `unknown` for exactly this reason
   (see types.ts). Rendering it with `{log.details}` used to throw React
   error #31 ("Objects are not valid as a React child") the moment a row
   like {"availability":"disabled"} showed up, which crashed the whole
   admin panel into its error boundary. `formatAuditDetails` (lib/auditDetails.ts)
   renders any of those shapes as safe, readable text -- see that file for
   the full rationale and for its unit tests (kept out of this component so
   it's importable from vitest without this file's '@/components/ui' /
   '@/lib/format' dependency chain).

   NOTE for the owner of lib/auditDetails.ts: `formatAuditDetails` joins
   array/object entries with the Persian comma «، » regardless of the
   panel's language, so an English-language audit row still reads with a
   Persian-punctuated details column. Flagged, not fixed here -- that file
   is out of this change's scope. */

/* The backend matches `action LIKE '<filter>%'` — a PREFIX, not a substring
   (admin_analytics.py). Every action name it stores is dotted and namespaced
   (`admin.user.ban`, `auth.login_failed`, `api_key.revoke`), so filters like
   a bare `ban`, `edit_user`, `create`, `delete` or `update` could not match a
   single row, and clicking any of them emptied the table. These are real
   prefixes, taken from the actions the code actually writes. There is no
   `unban` action: POST /admin/users/{uid}/ban is a toggle and logs
   `admin.user.ban` in both directions. */

export default function SecuritySection() {
  const lang = useLang()
  const s = securitySectionStrings(lang)
  const f = fmt(lang)

  const AUDIT_FILTERS = [
    { label: s.filterAll, value: '' },
    { label: s.filterAdmin, value: 'admin.' },
    { label: s.filterUsers, value: 'admin.user.' },
    { label: s.filterModels, value: 'admin.model.' },
    { label: s.filterPricing, value: 'admin.pricing.' },
    { label: s.filterApiKey, value: 'api_key.' },
    { label: s.filterAuth, value: 'auth.' },
  ]

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
      toast(s.unbanSuccess, 'success')
      reload()
    } catch (err) {
      toast(errMessage(err, s.unbanError), 'error')
    }
  }

  const pageCount = Math.max(1, Math.ceil(total / AUDIT_PAGE_SIZE))
  const threatColor = stats ? THREAT_COLOR[stats.threat_level] ?? THREAT_COLOR.low : THREAT_COLOR.low

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader
          title={s.title}
          subtitle={s.subtitle}
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
                <span className="text-xs text-muted">{s.threatLevelLabel}</span>
              </div>
              <p className="text-xl font-bold" style={{ color: threatColor }}>
                {s.threatLabel[stats.threat_level] ?? stats.threat_level}
              </p>
            </div>

            <StatCard icon="lock" label={s.failedLogins24h} value={f.num(stats.failed_logins_24h, { fallback: f.num(0) })} color="var(--danger)" />
            <StatCard icon="user" label={s.activeSessions} value={f.num(stats.active_sessions, { fallback: f.num(0) })} color="var(--info)" />
            <StatCard icon="security" label={s.bannedUsersCount} value={f.num(stats.banned_users?.length, { fallback: f.num(0) })} color="var(--warning)" />
          </div>

          {/* ─── Failed Login Chart (hand-rolled bars — no chart library) ─── */}
          <div className="admin-card">
            <div className="flex items-center gap-2 mb-4">
              <Icon name="chart" size={18} className="text-secondary" />
              <h3 className="font-semibold text-sm text-primary">
                {s.chartTitle}
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
                      title={s.chartTooltip(bar.hour, f.num(bar.count))}
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
              <h3 className="font-semibold text-sm text-primary">{s.bannedUsersTitle}</h3>
              <span className="badge badge-warning mr-auto">{f.num(stats.banned_users?.length, { fallback: f.num(0) })}</span>
            </div>
            {(stats.banned_users || []).length === 0 ? (
              <div className="text-center py-6 text-sm text-muted">
                {s.noBannedUsers}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="admin-table w-full text-sm">
                  <thead>
                    <tr>
                      <th className="text-right p-3">{s.colId}</th>
                      <th className="text-right p-3">{s.colUsername}</th>
                      <th className="text-right p-3">{s.colEmail}</th>
                      <th className="text-right p-3">{s.colBannedAt}</th>
                      <th className="text-right p-3">{s.colActions}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(stats.banned_users || []).map((u) => (
                      <tr key={u.id}>
                        <td className="p-3 text-xs font-mono">{u.id}</td>
                        <td className="p-3 text-sm text-primary">{u.username || '—'}</td>
                        <td className="p-3 text-xs text-secondary">{u.email}</td>
                        <td className="p-3 text-xs text-muted">{f.date(u.banned_at)}</td>
                        <td className="p-3">
                          <button
                            className="btn btn-sm"
                            style={{ background: 'var(--positive)', color: 'var(--text-on-accent)' }}
                            onClick={() => unbanUser(u.id)}
                          >
                            {s.unbanButton}
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
          <h3 className="font-semibold text-sm text-primary">{s.auditLogTitle}</h3>
          {loading && (
            <span className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin inline-block" />
          )}
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          {AUDIT_FILTERS.map((filterOpt) => (
            <button
              key={filterOpt.value}
              className={`btn btn-sm ${actionFilter === filterOpt.value ? 'font-bold' : ''}`}
              style={{
                background: actionFilter === filterOpt.value ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                color: actionFilter === filterOpt.value ? 'var(--accent)' : 'var(--text-secondary)',
              }}
              onClick={() => applyFilter(filterOpt.value)}
            >
              {filterOpt.label}
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
                  <th className="text-right p-3">{s.colId}</th>
                  <th className="text-right p-3">{s.colAction}</th>
                  <th className="text-right p-3">{s.colTargetType}</th>
                  <th className="text-right p-3">{s.colTargetId}</th>
                  <th className="text-right p-3">{s.colDetails}</th>
                  <th className="text-right p-3">{s.colTime}</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-sm text-muted">
                      {s.noAuditLogs}
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
                      <td className="p-3 text-xs text-secondary break-words max-w-md">{formatAuditDetails(log.details, lang)}</td>
                      <td className="p-3 text-xs text-muted">
                        {f.date(log.created_at)} {f.time(log.created_at)}
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
              {s.pageLabel(f.num(page), f.num(pageCount))}
            </span>
            <div className="flex gap-2">
              <button className="btn btn-sm" disabled={page <= 1 || loading} onClick={() => setPage(Math.max(1, page - 1))}>
                {s.prev}
              </button>
              <button className="btn btn-sm" disabled={page >= pageCount || loading} onClick={() => setPage(page + 1)}>
                {s.next}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
