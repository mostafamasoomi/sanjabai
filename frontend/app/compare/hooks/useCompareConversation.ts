import { useState, useRef, useEffect, useMemo } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { type ModelCatalogItem } from '@/types/catalog'
import { comparePageStrings } from '../page.strings'
import { type CompareTurn, type CompareSessionDetail } from './useCompareSessions'

/* ═══════════════════════════════════════════════════════════════════════════
   Owns the active comparison: the two per-side turn threads, the current
   session id (null until the first successful compare or a reopened
   history entry), and every send/open/reset action -- split out of
   page.tsx purely to stay under the house 500-line cap (same reason
   app/chat/page.tsx is thin JSX over useConversations.ts + useChatStream.ts).
   See the design spec at docs/superpowers/specs/2026-08-30-compare-
   history-continue-design.md for the request/response contract below.
   ═══════════════════════════════════════════════════════════════════════════ */

export type Side = 'a' | 'b'

type CompareResult = {
  model: string
  content: string
  elapsed: number
  input_tokens: number
  output_tokens: number
  cost: number
  error: string | null
}

type CompareResponse = {
  model_a: CompareResult
  model_b: CompareResult
  faster: 'model_a' | 'model_b' | null
  cheaper: 'model_a' | 'model_b' | null
  messages: { role: string; content: string }[]
  // Additive field per the design spec -- POST /v1/compare's response
  // shape is otherwise unchanged. Optional so this still type-checks
  // against a backend that hasn't landed the change yet.
  session_id?: number
}

type ContinueResponse = {
  model_a: CompareResult | null
  model_b: CompareResult | null
  faster: 'model_a' | 'model_b' | null
  cheaper: 'model_a' | 'model_b' | null
}

// Turns a single-model CompareResult (whatever /v1/compare or the continue
// endpoint returned for THIS side this turn) into the local per-turn shape
// the thread arrays keep. faster/cheaper are only ever true for the side
// that actually won a turn where BOTH models ran (see the design spec) --
// undefined (not false) so a solo-target turn never renders a stray badge.
function turnFromResult(result: CompareResult, faster: boolean, cheaper: boolean): CompareTurn {
  return {
    role: 'assistant',
    content: result.content,
    elapsed: result.elapsed,
    input_tokens: result.input_tokens,
    output_tokens: result.output_tokens,
    cost: result.cost,
    error: result.error,
    faster: faster || undefined,
    cheaper: cheaper || undefined,
  }
}

type UseCompareConversationParams = {
  models: ModelCatalogItem[]
  modelA: ModelCatalogItem | null
  modelB: ModelCatalogItem | null
  setModelA: (m: ModelCatalogItem) => void
  setModelB: (m: ModelCatalogItem) => void
  webSearch: boolean
  // The three history-hook actions this needs -- passed individually
  // (not the whole useCompareSessions() object) to match this codebase's
  // existing convention (see useConversations.ts's UseConversationsParams).
  openSession: (id: number) => Promise<CompareSessionDetail | null>
  deleteSession: (id: number, onDeleted?: () => void) => void
  refetchSessions: () => void
}

export function useCompareConversation({
  models, modelA, modelB, setModelA, setModelB, webSearch,
  openSession, deleteSession, refetchSessions,
}: UseCompareConversationParams) {
  const { token } = useAuth()
  const lang = useLang()
  const s = comparePageStrings(lang)
  const f = fmt(lang)

  const [comparedModelA, setComparedModelA] = useState<ModelCatalogItem | null>(null)
  const [comparedModelB, setComparedModelB] = useState<ModelCatalogItem | null>(null)
  // Requested model id/name for the active session, always available even
  // when the catalog entry above couldn't be matched (e.g. a reopened
  // session whose model has since been deprecated) -- see CompareResultPanel.
  const [labelA, setLabelA] = useState('')
  const [labelB, setLabelB] = useState('')

  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Session state -- null means "no comparison sent yet in this tab", the
  // first send in that state POSTs /v1/compare same as before this feature;
  // once a session_id comes back (or a history entry is opened) every
  // subsequent send goes through .../sessions/{id}/continue instead.
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [threadA, setThreadA] = useState<CompareTurn[]>([])
  const [threadB, setThreadB] = useState<CompareTurn[]>([])
  // Which side(s) the in-flight request is for, so the loading indicator
  // only appears under the column(s) actually waiting on a response.
  const [pendingTarget, setPendingTarget] = useState<'both' | Side | null>(null)

  // activeSessionIdRef lets deleteSession's callback (fired from inside the
  // sidebar hook, after the fact) check the CURRENT session id rather than
  // whatever it closed over -- same pattern as useConversations.ts's
  // activeConversationIdRef.
  const activeSessionIdRef = useRef<number | null>(null)
  useEffect(() => { activeSessionIdRef.current = sessionId }, [sessionId])

  const canSend = useMemo(() => {
    if (busy || !prompt.trim()) return false
    if (!sessionId) return !!modelA && !!modelB && modelA.id !== modelB.id
    return true
  }, [modelA, modelB, prompt, busy, sessionId])

  const startNewComparison = () => {
    if (busy) return
    setSessionId(null)
    setThreadA([])
    setThreadB([])
    setComparedModelA(null)
    setComparedModelB(null)
    setLabelA('')
    setLabelB('')
    setPrompt('')
    setError('')
  }

  const handleOpenSession = async (id: number) => {
    if (busy) return
    const detail = await openSession(id)
    if (!detail) return
    setSessionId(detail.id)
    setThreadA(detail.thread_a)
    setThreadB(detail.thread_b)
    setError('')
    setPrompt('')
    setLabelA(detail.model_a_requested)
    setLabelB(detail.model_b_requested)
    // Match the session's REQUESTED model id/name against the live catalog
    // for display name + price band -- GET .../sessions/{id} never echoes
    // the resolved provider_model_id (see CompareSessionDetail's comment),
    // and may legitimately miss anyway (deprecated/renamed model), in which
    // case CompareResultPanel falls back to the plain requested label.
    const foundA = models.find(m => m.providerModelId === detail.model_a_requested || m.id === detail.model_a_requested)
    const foundB = models.find(m => m.providerModelId === detail.model_b_requested || m.id === detail.model_b_requested)
    setComparedModelA(foundA || null)
    setComparedModelB(foundB || null)
    if (foundA) setModelA(foundA)
    if (foundB) setModelB(foundB)
  }

  const handleDeleteSession = (id: number) => {
    deleteSession(id, () => {
      if (activeSessionIdRef.current === id) startNewComparison()
    })
  }

  const extractErrorMessage = async (res: Response): Promise<string> => {
    const errData = await res.json().catch(() => ({}))
    // errData?.error?.message / errData?.detail are backend-sourced error
    // messages (Persian only for now) -- see the i18n handoff report.
    if (res.status === 429) return 'INSUFFICIENT_BALANCE'
    return errData?.error?.message || errData?.detail || s.serverError(f.num(res.status))
  }

  const handleSend = async (target: 'both' | Side) => {
    const text = prompt.trim()
    if (!text || busy) return
    if (!sessionId && (!modelA || !modelB || modelA.id === modelB.id)) return

    setBusy(true)
    setError('')
    setPendingTarget(sessionId ? target : 'both')

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    try {
      if (!sessionId) {
        // First message in this tab -- always both models, same as the
        // page's original single-shot behavior. The per-side buttons are
        // only rendered once a session exists (page.tsx), so `target` here
        // is always 'both' in practice.
        const res = await apiFetch('/api/v1/compare', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            model_a: modelA!.providerModelId || modelA!.id,
            model_b: modelB!.providerModelId || modelB!.id,
            messages: [{ role: 'user', content: text }],
            ...(webSearch ? { web_search: true } : {}),
          }),
        })

        if (!res.ok) {
          const msg = await extractErrorMessage(res)
          throw new Error(msg)
        }

        const data: CompareResponse = await res.json()
        setComparedModelA(modelA)
        setComparedModelB(modelB)
        setLabelA(modelA!.providerModelId || modelA!.id)
        setLabelB(modelB!.providerModelId || modelB!.id)
        setThreadA([
          { role: 'user', content: text },
          turnFromResult(data.model_a, data.faster === 'model_a', data.cheaper === 'model_a'),
        ])
        setThreadB([
          { role: 'user', content: text },
          turnFromResult(data.model_b, data.faster === 'model_b', data.cheaper === 'model_b'),
        ])
        if (data.session_id != null) {
          setSessionId(data.session_id)
          refetchSessions()
        }
        setPrompt('')
      } else {
        const res = await apiFetch(`/api/v1/compare/sessions/${sessionId}/continue`, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            target,
            content: text,
            ...(webSearch ? { web_search: true } : {}),
          }),
        })

        if (!res.ok) {
          const msg = await extractErrorMessage(res)
          throw new Error(msg)
        }

        const data: ContinueResponse = await res.json()
        const resultA = data.model_a
        const resultB = data.model_b
        if (resultA) {
          setThreadA(prev => [
            ...prev,
            { role: 'user', content: text },
            turnFromResult(resultA, data.faster === 'model_a', data.cheaper === 'model_a'),
          ])
        }
        if (resultB) {
          setThreadB(prev => [
            ...prev,
            { role: 'user', content: text },
            turnFromResult(resultB, data.faster === 'model_b', data.cheaper === 'model_b'),
          ])
        }
        setPrompt('')
        refetchSessions()
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : s.connectionError
      setError(msg === 'INSUFFICIENT_BALANCE' ? s.insufficientBalance : msg)
    } finally {
      setBusy(false)
      setPendingTarget(null)
    }
  }

  return {
    comparedModelA, comparedModelB, labelA, labelB,
    prompt, setPrompt, busy, error,
    sessionId, threadA, threadB, pendingTarget,
    canSend,
    startNewComparison, handleOpenSession, handleDeleteSession, handleSend,
  }
}
