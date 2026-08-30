import { useState, useCallback, useEffect } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { comparePageStrings } from '../page.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Compare session history — list/open/delete, mirrors the shape of
   app/chat/hooks/useConversations.ts, adapted for two-model compare
   sessions. Endpoints per the design spec (docs/superpowers/specs/
   2026-08-30-compare-history-continue-design.md):
     GET    /v1/compare/sessions          -- paginated list, thread bodies
                                              excluded (same reason as
                                              GET /conversations)
     GET    /v1/compare/sessions/{id}     -- full row incl. both threads
     DELETE /v1/compare/sessions/{id}
   Reached through /api/v1/compare/sessions* -- there is no dedicated
   route.ts for these (only /api/v1/compare itself has one, see that
   file); the generic catch-all at app/api/[...path]/route.ts already
   proxies GET/POST/PUT/DELETE with Authorization/Cookie/X-Requested-With
   forwarded, which is all these plain-JSON endpoints need.
   ═══════════════════════════════════════════════════════════════════════════ */

// Persisted turns only ever carry {role, content} -- compare_sessions.
// thread_a/thread_b are a JSONB array of that shape (see the spec's data
// model), no per-turn timing/token/cost stats. Turns produced live in this
// tab (via /v1/compare or a continue call) carry the extra fields; see
// CompareTurn's use in page.tsx for where those get attached.
export type CompareTurn = {
  role: 'user' | 'assistant'
  content: string
  elapsed?: number
  input_tokens?: number
  output_tokens?: number
  cost?: number
  error?: string | null
  faster?: boolean
  cheaper?: boolean
}

export type CompareSessionSummary = {
  id: number
  title: string
  model_a_requested: string
  model_b_requested: string
  created_at: string
  updated_at: string
}

export type CompareSessionDetail = CompareSessionSummary & {
  // GET /v1/compare/sessions/{id} deliberately does NOT echo the resolved
  // provider_model_id (backend/chat_compare_sessions.py's get_compare_session)
  // -- same no-provider-leak rule as everywhere else in this codebase (see
  // content.py). Only the ORIGINALLY REQUESTED model id/name is ever sent
  // to a normal user, which is why CompareSessionSummary's
  // model_a_requested/model_b_requested are what page.tsx matches against
  // the live catalog, not a model_a/model_b field that doesn't exist here.
  thread_a: CompareTurn[]
  thread_b: CompareTurn[]
}

type UseCompareSessionsParams = {
  token: string | null
}

export function useCompareSessions({ token }: UseCompareSessionsParams) {
  const lang = useLang()
  const s = comparePageStrings(lang)
  const [sessions, setSessions] = useState<CompareSessionSummary[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)

  const authHeaders = useCallback((): Record<string, string> => {
    return token ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' }
  }, [token])

  const fetchSessions = useCallback(async () => {
    if (!token) return
    setLoadingSessions(true)
    try {
      const res = await fetch('/api/v1/compare/sessions', { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        // Same defensive shape-handling as useConversations.fetchConversations
        // -- backend may return a bare array or a paginated {items: [...]}.
        const list = Array.isArray(data) ? data : (data?.items ?? [])
        setSessions(list)
      }
    } catch { /* silent -- same as useConversations.fetchConversations */ }
    finally { setLoadingSessions(false) }
  }, [token, authHeaders])

  useEffect(() => { fetchSessions() }, [fetchSessions])

  const openSession = useCallback(async (id: number): Promise<CompareSessionDetail | null> => {
    if (!token) return null
    try {
      const res = await fetch(`/api/v1/compare/sessions/${id}`, { headers: authHeaders() })
      if (!res.ok) throw new Error('failed')
      return (await res.json()) as CompareSessionDetail
    } catch {
      toast(s.loadSessionFailed, 'error')
      return null
    }
  }, [token, authHeaders, s])

  const deleteSession = useCallback(async (id: number, onDeleted?: () => void) => {
    if (!token) return
    setDeletingId(id)
    try {
      const res = await apiFetch(`/api/v1/compare/sessions/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      })
      if (res.ok) {
        setSessions(prev => prev.filter(sess => sess.id !== id))
        onDeleted?.()
      }
    } catch {
      toast(s.deleteSessionFailed, 'error')
    } finally {
      setDeletingId(null)
      setConfirmDeleteId(null)
    }
  }, [token, authHeaders, s])

  return {
    sessions,
    loadingSessions,
    fetchSessions,
    deletingId,
    confirmDeleteId, setConfirmDeleteId,
    openSession,
    deleteSession,
  }
}
