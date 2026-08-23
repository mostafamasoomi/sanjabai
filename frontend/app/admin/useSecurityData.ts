/* Data for the security (SOC) screen.
 *
 * Split out of SecuritySection.tsx to keep that file under the 500-line cap.
 *
 * Two independent feeds, two independent error states — GET
 * /admin/security/stats is a much newer route than GET /admin/audit-logs,
 * and one being down must not blank the other.
 *
 * Pagination lives here as state, and `load` is derived from it. The old
 * version called `setAuditPage(n)` and then invoked a `loadSecurityData`
 * closure captured at the previous page, so "بعدی" re-fetched the page it
 * was already on and the table never advanced.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, errMessage } from './api'
import type { SecurityStats, AuditLog } from './types'

export const AUDIT_PAGE_SIZE = 50
const REFRESH_MS = 30_000

export function useSecurityData() {
  const [stats, setStats] = useState<SecurityStats | null>(null)
  const [statsError, setStatsError] = useState<string | null>(null)
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [logsError, setLogsError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [actionFilter, setActionFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const query = `page=${page}&limit=${AUDIT_PAGE_SIZE}` + (actionFilter ? `&action=${encodeURIComponent(actionFilter)}` : '')
    const [statsRes, logsRes] = await Promise.allSettled([
      api('/api/admin/security/stats'),
      api(`/api/admin/audit-logs?${query}`),
    ])

    if (statsRes.status === 'fulfilled') {
      setStats(await statsRes.value.json())
      setStatsError(null)
    } else {
      // Previously swallowed, which left the four stat cards on their
      // skeleton forever — indistinguishable from a slow load.
      setStats(null)
      setStatsError(errMessage(statsRes.reason, 'خطا در دریافت آمار امنیتی'))
    }

    if (logsRes.status === 'fulfilled') {
      const body = await logsRes.value.json()
      // The response key is `logs` (admin_analytics.py). The panel used to
      // read `events` / `security_events` / `audit_logs`, none of which the
      // server has ever sent, so the audit table was always empty.
      setLogs(Array.isArray(body?.logs) ? body.logs : [])
      setTotal(typeof body?.total === 'number' ? body.total : 0)
      setLogsError(null)
    } else {
      setLogs([])
      setTotal(0)
      setLogsError(errMessage(logsRes.reason, 'خطا در دریافت لاگ عملیات ادمین'))
    }

    setLoading(false)
  }, [page, actionFilter])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  /** Switching the filter always returns to page 1 — page 3 of "ban" is not
      the same slice as page 3 of "همه". */
  const applyFilter = useCallback((action: string) => {
    setActionFilter(action)
    setPage(1)
  }, [])

  return {
    stats, statsError, logs, logsError, total, page, setPage,
    actionFilter, applyFilter, loading, reload: load, setStats,
  }
}
