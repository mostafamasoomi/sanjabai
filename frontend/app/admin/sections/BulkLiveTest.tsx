'use client'

import { useRef, useState } from 'react'
import { toast } from '@/components/ui'
import { faNum } from '@/lib/format'
import { errMessage } from '../api'

/* ═══════════════════════════════════════════════════════════════════════════
   Bulk «تست زنده» — run the per-model live probe over a selection.

   Deliberately NOT a new bulk endpoint. Each model is one call to the
   existing POST /admin/models/{id}/test, because that route's whole job is to
   spend up to ~26s on one upstream (admin_pricing._ADMIN_PROBE_BUDGET_S), and
   the browser reaches the API through a Next.js rewrite that hard-caps at
   30s. A server-side bulk probe of even ten models could not answer inside
   that cap; a hundred calls of one model each always can, and the admin gets
   a live count instead of a spinner that either returns in twenty minutes or
   500s.

   Why this exists at all: /test used to display its result and discard it,
   so «تست زنده» could not satisfy the enable-gate it was advertised as
   satisfying (backend/model_health_record.record_probe_sample). Now that a
   successful test genuinely makes a model enableable, doing it one row at a
   time across 1,156 parked models is not a workflow.

   Own file because ModelOpsSection.tsx is past the project's 500-line cap.
   ═══════════════════════════════════════════════════════════════════════════ */

/** The concurrency is small on purpose: these probes go to the same three
 *  upstream routers the site serves traffic through, and the failure this
 *  whole feature exists to work around — «All credentials are cooling down» —
 *  is a rate limit. Testing faster produces more cooldowns, not more answers. */
const BULK_TEST_CONCURRENCY = 3

/** Above this, a run is long enough that the admin should be told the rough
 *  cost in time before starting it rather than after. At 3 at a time and a
 *  few seconds each, 200 models is already several minutes. */
const BULK_TEST_WARN_ABOVE = 200

export interface TestResult {
  ok: boolean
  latency_ms: number | null
  error: string | null
  status_code: number | null
}

export interface BulkTestState {
  total: number
  done: number
  ok: number
  cancel: boolean
}

interface UseBulkLiveTestArgs {
  api: (path: string, opts?: RequestInit) => Promise<Response>
  /** Merged into the caller's per-row result map when the run finishes. */
  onResults: (results: Record<string, TestResult>) => void
  /** Every probe moves the row's health state, so the table is refetched. */
  onDone: () => Promise<void> | void
}

export function useBulkLiveTest({ api, onResults, onDone }: UseBulkLiveTestArgs) {
  const [bulkTest, setBulkTest] = useState<BulkTestState | null>(null)
  // The live, mutable run object. `bulkTest` is a render-only snapshot of it,
  // so «توقف» has to reach through this ref to actually stop the workers, and
  // the workers have to read progress from here rather than from React state,
  // which would be a stale snapshot on every tick.
  const runRef = useRef<BulkTestState | null>(null)

  const cancel = () => {
    if (runRef.current) runRef.current.cancel = true
    setBulkTest((prev) => (prev ? { ...prev, cancel: true } : prev))
  }

  const run = async (ids: string[]) => {
    if (ids.length === 0) { toast('ابتدا حداقل یک مدل را انتخاب کنید', 'error'); return }
    if (ids.length > BULK_TEST_WARN_ABOVE) {
      const minutes = Math.ceil((ids.length * 4) / BULK_TEST_CONCURRENCY / 60)
      if (!window.confirm(
        `${ids.length} مدل انتخاب شده است. تست زندهٔ همهٔ آن‌ها حدود ${minutes} دقیقه طول می‌کشد `
        + 'و در همین صفحه اجرا می‌شود (با بستن صفحه متوقف می‌شود). ادامه می‌دهید؟',
      )) return
    }

    const state: BulkTestState = { total: ids.length, done: 0, ok: 0, cancel: false }
    runRef.current = state
    setBulkTest({ ...state })

    const results: Record<string, TestResult> = {}
    let cursor = 0
    const worker = async () => {
      while (!state.cancel) {
        const i = cursor++
        if (i >= ids.length) return
        const id = ids[i]
        try {
          const res = await api(`/api/admin/models/${encodeURIComponent(id)}/test`, { method: 'POST' })
          const body = await res.json()
          results[id] = {
            ok: !!body.ok, latency_ms: body.latency_ms ?? null,
            error: body.error ?? null, status_code: body.status_code ?? null,
          }
          if (body.ok) state.ok += 1
        } catch (err) {
          // One unreachable model must not abort the other 199. The reason is
          // kept per row so the admin can see WHICH failed and why.
          results[id] = { ok: false, latency_ms: null, error: errMessage(err, 'خطای شبکه'), status_code: null }
        } finally {
          state.done += 1
          setBulkTest({ ...state })
        }
      }
    }

    await Promise.all(Array.from({ length: Math.min(BULK_TEST_CONCURRENCY, ids.length) }, worker))
    onResults(results)
    runRef.current = null
    setBulkTest(null)
    toast(
      state.cancel
        ? `تست متوقف شد — ${faNum(state.ok)} مدل سالم از ${faNum(state.done)} مدل آزموده‌شده`
        : `${faNum(state.ok)} مدل از ${faNum(state.total)} مدل سالم بود`,
      state.ok > 0 ? 'success' : 'error',
    )
    await onDone()
  }

  return { bulkTest, run, cancel }
}

export function BulkLiveTestProgress({ state, onCancel }: { state: BulkTestState; onCancel: () => void }) {
  return (
    <div className="admin-card admin-row gap-3"
         style={{ borderRight: '3px solid var(--accent, #6366f1)' }}>
      <span className="w-4 h-4 border-2 rounded-full animate-spin inline-block shrink-0"
            style={{ borderColor: 'var(--border)', borderTopColor: 'var(--accent, #6366f1)' }} />
      <span className="text-sm text-primary">
        در حال تست زنده: {faNum(state.done)} از {faNum(state.total)} — {faNum(state.ok)} مدل سالم
      </span>
      {/* Progress is a plain div, not a chart: recharts breaks the build
          (documented in AdminCharts.tsx). */}
      <div className="h-1 rounded flex-1" style={{ minWidth: 120, background: 'var(--border)' }}>
        <div className="h-1 rounded" style={{
          width: `${Math.round((state.done / Math.max(1, state.total)) * 100)}%`,
          background: 'var(--accent, #6366f1)',
        }} />
      </div>
      <button className="btn btn-sm" onClick={onCancel}>توقف</button>
    </div>
  )
}
