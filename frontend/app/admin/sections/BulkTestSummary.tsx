'use client'

import { useMemo, useState } from 'react'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { errMessage } from '../api'
import type { TestResult } from './BulkLiveTest'
import { bulkTestSummaryStrings } from './BulkTestSummary.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   The other half of «تست زنده» that useBulkLiveTest/BulkLiveTestProgress
   (BulkLiveTest.tsx) do not provide: what to DO with a finished run.

   Today a bulk run over 200+ parked models ends in a toast ("N of M
   succeeded") and a per-row error string — a 404 (model gone forever) and a
   429 (retry in a minute) read identically in that list, and there is no
   action on the answer. This groups the same `Record<string, TestResult>`
   BulkLiveTest already produces by what the failure actually MEANS, and
   offers exactly one bulk action: disabling the 404 group, because that is
   the only class where "the model is gone" is not a guess.

   Deliberately offers NOTHING for 429/401/403/402/5xx/timeout beyond display:
   - 429/timeout/5xx are moments, not verdicts (see providers.py
     TRANSIENT_PROBE_REASONS) — disabling on one bad probe would withdraw
     models that work.
   - 401/403/402 are about OUR supplying account, not the model — a separate,
     ongoing concern; pre-empting it here with a destructive bulk action
     would be wrong.
   Restraint here is the point, not a missing feature.

   Own file: ModelOpsSection.tsx is already at the project's 500-line cap.
   ═══════════════════════════════════════════════════════════════════════════ */

export type ErrorClass = 'gone' | 'rateLimited' | 'accessLost' | 'noCredit' | 'upstreamBroken' | 'timeout' | 'other'

/** Fixed so `bulkTestSummaryStrings().groupLabel`/`groupHint` — plain
 *  objects keyed by this same union — stay a compile-time completeness
 *  check rather than a runtime lookup that can silently return undefined. */
const ERROR_CLASSES: readonly ErrorClass[] = ['gone', 'rateLimited', 'accessLost', 'noCredit', 'upstreamBroken', 'timeout', 'other']

/** One TestResult -> its class. Mirrors backend/providers.py exactly:
 *  `probe_model` sets `error = f'http_{status_code}'` and echoes that same
 *  int in `status_code` for any 4xx/5xx response, so status_code is the
 *  reliable signal; only exception-based failures (ReadTimeout,
 *  JSONDecodeError, ...) leave status_code null and have to be read off the
 *  `error` string instead. Never called on an `ok` result — callers filter
 *  those out first, so there is no "success" class to keep in sync here. */
function classifyOne(r: TestResult): ErrorClass {
  const code = r.status_code
  if (code === 404) return 'gone'
  if (code === 429) return 'rateLimited'
  if (code === 401 || code === 403) return 'accessLost'
  if (code === 402) return 'noCredit'
  if (code !== null && code >= 500 && code < 600) return 'upstreamBroken'
  // ReadTimeout/ConnectTimeout/asyncio's literal 'timeout' all carry no
  // status_code — the exception name is the only signal left.
  if ((r.error || '').toLowerCase().includes('timeout')) return 'timeout'
  return 'other'
}

/** Exported for the unit test: pure, no React, no network. Groups only the
 *  FAILED entries (`ok === false`) — an `ok` probe has no error to classify.
 *  Every key in ERROR_CLASSES is always present, even at zero, so a caller
 *  can iterate `Object.entries` without an unlisted class vanishing. */
export function classifyFailures(results: Record<string, TestResult>): Record<ErrorClass, string[]> {
  const groups = Object.fromEntries(ERROR_CLASSES.map((c) => [c, [] as string[]])) as Record<ErrorClass, string[]>
  for (const [id, r] of Object.entries(results)) {
    if (r.ok) continue
    groups[classifyOne(r)].push(id)
  }
  return groups
}

interface BulkTestSummaryProps {
  /** The finished run's results — same shape ModelOpsSection already keeps
   *  in `testResults`, passed in rather than re-fetched. */
  results: Record<string, TestResult>
  api: (path: string, opts?: RequestInit) => Promise<Response>
  /** The caller's existing table refetch (ModelOpsSection's `load`) — reused
   *  rather than this component inventing a second one. */
  onDone: () => Promise<void> | void
}

export default function BulkTestSummary({ results, api, onDone }: BulkTestSummaryProps) {
  const lang = useLang()
  const s = bulkTestSummaryStrings(lang)
  const f = fmt(lang)
  const [disabling, setDisabling] = useState(false)
  // Ids the admin already disabled from THIS panel, kept locally so the
  // "gone" group and its button reflect the action immediately without
  // waiting on the parent to re-run the whole bulk test.
  const [disabledIds, setDisabledIds] = useState<Set<string>>(new Set())

  const groups = useMemo(() => {
    const live = Object.fromEntries(
      Object.entries(results).filter(([id]) => !disabledIds.has(id)),
    )
    return classifyFailures(live)
  }, [results, disabledIds])

  const total = Object.keys(results).length - disabledIds.size
  const okCount = Object.values(results).filter((r) => r.ok).length
  const failedCount = total - okCount

  const ordered = ERROR_CLASSES
    .map((cls) => ({ cls, ids: groups[cls] }))
    .filter((g) => g.ids.length > 0)
    .sort((a, b) => b.ids.length - a.ids.length)

  const disableGone = async () => {
    const ids = groups.gone
    if (ids.length === 0) return
    if (!window.confirm(s.confirmDisableGone(f.num(ids.length)))) return
    setDisabling(true)
    try {
      const res = await api('/api/admin/models/bulk-availability', {
        method: 'POST',
        body: JSON.stringify({ ids, availability: 'disabled' }),
      })
      const body = await res.json()
      toast(s.disabledSuccess(f.num(body.updated ?? ids.length)), 'success')
      setDisabledIds((prev) => new Set([...prev, ...ids]))
      await onDone()
    } catch (err) {
      toast(errMessage(err, s.disableFailed), 'error')
    } finally {
      setDisabling(false)
    }
  }

  if (total <= 0) return null

  return (
    <div className="admin-card" style={{ borderRight: '3px solid var(--accent, #6366f1)' }}>
      <h3 className="font-bold text-primary text-sm mb-1">{s.title}</h3>
      <p className="text-xs text-muted mb-3">{s.summary(f.num(total), f.num(okCount), f.num(failedCount))}</p>

      <div className="space-y-2">
        {ordered.map(({ cls, ids }) => (
          <div key={cls} className="admin-row gap-3" style={{ alignItems: 'flex-start' }}>
            <span className="text-xs px-2 py-1 rounded-full shrink-0" style={{ background: 'var(--bg-elevated)', minWidth: 36, textAlign: 'center' }}>
              {f.num(ids.length)}
            </span>
            <div className="flex-1">
              <div className="text-sm text-primary">{s.groupLabel[cls]}</div>
              <div className="text-xs text-muted">{s.groupHint[cls]}</div>
            </div>
            {cls === 'gone' && (
              <button className="btn btn-sm shrink-0" onClick={disableGone} disabled={disabling}>
                {disabling ? s.disabling : s.disableGoneAction(f.num(ids.length))}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
