import { useState, useEffect, useCallback, useMemo } from 'react'
import { toast } from '@/components/ui'
import { modelColor, modelName } from '../usageHelpers'
import type { UsageData } from '../usageTypes'

/* ═══════════════════════════════════════════════════════════════════════════
   Fetches usage data + CSV export, and derives all the per-model / summary
   values the page renders. Split out of page.tsx verbatim -- no behaviour
   change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function useUsageData(token: string | null) {
  const [data, setData] = useState<UsageData | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchUsage = useCallback(async (silent = false) => {
    if (!token) return
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const res = await fetch('/api/me/usage', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) {
        const d = await res.json()
        // Normalise the collections up front. Every derived value below is a
        // useMemo that maps/filters/reduces over them, so one missing key in
        // the response — an older backend, a user with no history — threw
        // during render and the error boundary replaced the whole page with
        // "خطای سیستمی". Defaulting here keeps that a legitimate empty state.
        setData({
          ...d,
          recent_events: Array.isArray(d?.recent_events) ? d.recent_events : [],
          per_model_breakdown: Array.isArray(d?.per_model_breakdown) ? d.per_model_breakdown : [],
        })
      } else {
        toast('خطا در دریافت اطلاعات مصرف', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [token])

  useEffect(() => {
    if (!token) { setLoading(false); return }
    fetchUsage()
  }, [token, fetchUsage])

  /* ── Derived: most expensive of the recent events ──
     Scoped to the (server-truncated) recent_events list, so it is labelled
     "اخیر" in the UI rather than presented as an all-time maximum. */
  const mostExpensive = useMemo(() => {
    if (!data || data.recent_events.length === 0) return null
    return data.recent_events.reduce((m, e) => (e.cost > m.cost ? e : m), data.recent_events[0])
  }, [data])

  /* ── Derived: per-model token efficiency + cost share ── */
  const modelStats = useMemo(() => {
    if (!data) return []
    return data.per_model_breakdown.map((m, i) => {
      const totalTokens = m.input_tokens + m.output_tokens
      const avgTokensPerCall = m.calls > 0 ? totalTokens / m.calls : 0
      const costPerCall = m.calls > 0 ? m.cost / m.calls : 0
      return {
        ...m,
        index: i,
        color: modelColor(i),
        name: modelName(m.model),
        totalTokens,
        avgTokensPerCall,
        costPerCall,
      }
    })
  }, [data])

  const totalModelCost = useMemo(
    () => modelStats.reduce((s, m) => s + m.cost, 0) || 1,
    [modelStats],
  )

  const donutData = useMemo(
    () => modelStats.map((m) => ({ label: m.name, value: m.cost, color: m.color })),
    [modelStats],
  )

  /* ── Export CSV ──
     Pulls the authoritative, complete export from the server
     (backend/admin_usage_me.py `/me/usage/export`) rather than serialising the
     20-row recent_events list the page holds — the download must not be a
     silently truncated slice of the user's history. */
  const exportCsv = useCallback(async () => {
    if (!token) return
    try {
      const res = await fetch('/api/me/usage/export?format=csv', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        toast('خطا در دریافت فایل CSV', 'error')
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `usage-${new Date().toISOString().slice(0, 10)}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast('فایل CSV دانلود شد', 'success')
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    }
  }, [token])

  const totalTokens = (data?.total_input_tokens_this_month ?? 0) + (data?.total_output_tokens_this_month ?? 0)
  const maxModelCost = Math.max(...(data?.per_model_breakdown.map(m => m.cost) ?? [1]), 1)
  const hasAnyData = (data?.per_model_breakdown.length ?? 0) > 0 || (data?.recent_events.length ?? 0) > 0
  const recentEvents = data?.recent_events ?? []

  return {
    data,
    loading,
    refreshing,
    fetchUsage,
    exportCsv,
    mostExpensive,
    modelStats,
    totalModelCost,
    donutData,
    totalTokens,
    maxModelCost,
    hasAnyData,
    recentEvents,
  }
}
