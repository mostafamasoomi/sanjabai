'use client'

import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { errMessage } from '../api'
import { SectionHeader, StatCard } from './shared'
import { routerProbeStrings } from './RouterProbeSection.strings'
import { elapsedParts } from './upstreamOverheadHelpers'
import {
  parseRouterProbeResponse,
  isProbeStale,
  type ParsedRouterProbe,
  type RouterProbeRow,
  type RouterProbeState,
} from './routerProbeHelpers'

/* ═══════════════════════════════════════════════════════════════════════════
   Smart-router acceptance probe — admin surface for backend/admin_smart_router.py
   (backed by services/router_probe.py; read that module's docstring first, it
   carries the full design rationale). Before this section existed, the two
   routes it drives had no caller anywhere in the app — reachable only with
   curl, which in practice meant the probe would never run and the router
   would stay permanently ineligible.

   Same shape as ./UpstreamOverheadSection.tsx: an expensive live measurement
   behind an admin button, whose persisted result is read back and displayed.
   The parsing/classification logic lives in ./routerProbeHelpers.ts, not
   here, for the same reason UpstreamOverheadSection.tsx's does — this repo's
   vitest has no jsdom, a component's JSX is untestable, so display-DECISION
   logic must live in a plain .ts sibling.

   Server contract — pinned against admin_smart_router.py + router_probe.py:
     GET  /admin/smart-router/probe  -> { stored: { version, measured_at,
                                           results }, storedUpdatedAt }
     POST /admin/smart-router/probe  -> runs run_probe_scan() LIVE (up to 12
                                         models x 4 calls each, real upstream
                                         money) and returns { status,
                                         measured, eligible, value } where
                                         `value` is shaped like GET's
                                         `stored`. This section re-fetches GET
                                         afterwards for the canonical view
                                         (including storedUpdatedAt), the same
                                         "measure re-runs, get reads back"
                                         split UpstreamOverheadSection uses.

   🚨 The stored `results` map is keyed by `Candidate.public_id` — never a
   provider or upstream name (see router_probe.py's module docstring and
   routerProbeHelpers.ts's contract note). This component renders exactly
   the fields routerProbeHelpers.ts extracts and never fetches anything else
   to "enrich" a row.

   🚨 The run button fires up to 48 live model calls that cost real money.
   The hint text next to it says so, in Persian, with no invented number
   (the cost depends on live prices) — and the action itself is gated behind
   `window.confirm`, the same pattern BulkTestSummary.tsx's disable-gone
   action already uses in this codebase.
   ═══════════════════════════════════════════════════════════════════════════ */

interface RouterProbeSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

/** Mirrors UpstreamOverheadSection.tsx's identical helper: `۴۲ ثانیه` under a
 *  minute, `۱ دقیقه و ۵ ثانیه` past it, so a long-running probe reads as
 *  "still going" rather than looking hung. */
function formatElapsedSeconds(
  ms: number,
  s: ReturnType<typeof routerProbeStrings>,
  f: ReturnType<typeof fmt>,
): string {
  const { minutes, seconds } = elapsedParts(ms)
  if (minutes === 0) return s.elapsedSeconds(f.num(seconds))
  return seconds === 0 ? s.elapsedMinutes(f.num(minutes)) : s.elapsedMinutesSeconds(f.num(minutes), f.num(seconds))
}

/** The raw `reason` string (from routerProbeHelpers.ts, never a provider
 *  field — see the header) -> a human sentence. Display text, not a display
 *  DECISION, so it lives here rather than in the helpers module; the
 *  decision itself (which of the three outcomes a row is) is what
 *  routerProbeHelpers.ts's classifyEntry is unit-tested against. */
function reasonLabel(reason: string | null, s: ReturnType<typeof routerProbeStrings>): string {
  if (!reason) return s.noReason
  if (reason === 'bad_shape') return s.reasonBadShape
  if (reason === 'no_discrimination') return s.reasonNoDiscrimination
  if (reason === 'provider_not_configured') return s.reasonProviderNotConfigured
  if (reason === 'transient_timeout') return s.reasonTransientTimeout
  if (reason === 'transient_exception') return s.reasonTransientException
  const httpMatch = /^transient_http_(\d+)$/.exec(reason)
  if (httpMatch) return s.reasonTransientHttp(httpMatch[1])
  return s.reasonUnknown(reason)
}

function stateBadgeStyle(state: RouterProbeState): { background: string; color: string } {
  if (state === 'eligible') return { background: 'var(--success-dim, rgba(34,197,94,.12))', color: 'var(--success, #22c55e)' }
  if (state === 'ineligibleTransient') return { background: 'var(--warning-dim, rgba(234,179,8,.12))', color: 'var(--warning, #eab308)' }
  return { background: 'var(--danger-dim)', color: 'var(--danger)' }
}

function stateLabel(state: RouterProbeState, s: ReturnType<typeof routerProbeStrings>): string {
  if (state === 'eligible') return s.stateEligible
  if (state === 'ineligibleTransient') return s.stateIneligibleTransient
  return s.stateIneligiblePermanent
}

export default function RouterProbeSection({ api }: RouterProbeSectionProps) {
  const lang = useLang()
  const s = routerProbeStrings(lang)
  const f = fmt(lang)
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<ParsedRouterProbe | null>(null)
  const [loadError, setLoadError] = useState(false)

  const [measuring, setMeasuring] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)
  const measureStart = useRef<number | null>(null)

  const load = async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const res = await api('/api/admin/smart-router/probe')
      const body = await res.json()
      setData(parseRouterProbeResponse(body))
    } catch (err) {
      setData(null)
      setLoadError(true)
      toast(errMessage(err, s.loadErrorToast), 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // Mount-only, same as UpstreamOverheadSection.tsx: a language toggle
    // re-renders the already-parsed data through `s`/`f`, it does not need a
    // fresh round-trip. `load` is always current on the retry/measure paths.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!measuring) return
    const id = setInterval(() => {
      if (measureStart.current != null) setElapsedMs(Date.now() - measureStart.current)
    }, 500)
    return () => clearInterval(id)
  }, [measuring])

  const runMeasure = async () => {
    if (!window.confirm(s.confirmRun)) return
    setMeasuring(true)
    setElapsedMs(0)
    measureStart.current = Date.now()
    try {
      const res = await api('/api/admin/smart-router/probe', { method: 'POST' })
      const body = await res.json()
      const measuredCount = typeof body?.measured === 'number' ? body.measured : null
      const eligibleCount = typeof body?.eligible === 'number' ? body.eligible : null
      await load()
      toast(
        measuredCount != null && eligibleCount != null
          ? s.measureDone(f.num(measuredCount), f.num(eligibleCount))
          : s.measureFailedToast,
        'success',
      )
    } catch (err) {
      toast(errMessage(err, s.measureFailedToast), 'error')
    } finally {
      setMeasuring(false)
      measureStart.current = null
    }
  }

  const eligibleCount = data ? data.rows.filter((r) => r.state === 'eligible').length : 0
  const permanentCount = data ? data.rows.filter((r) => r.state === 'ineligiblePermanent').length : 0
  const transientCount = data ? data.rows.filter((r) => r.state === 'ineligibleTransient').length : 0
  const stale = data ? isProbeStale(data.measuredAt) : false

  return (
    <div className="space-y-6">
      <SectionHeader title={s.title} subtitle={s.subtitle} />

      <div className="admin-card">
        <div className="flex items-center justify-between gap-4 flex-wrap mb-2">
          <h3 className="font-semibold text-sm text-primary">{s.liveMeasurementTitle}</h3>
          <button className="btn btn-sm" onClick={runMeasure} disabled={measuring}>
            {measuring ? (
              <>
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                <span>{s.measuring(formatElapsedSeconds(elapsedMs, s, f))}</span>
              </>
            ) : (
              <>
                <Icon name="refresh" size={14} />
                <span>{s.measureButton}</span>
              </>
            )}
          </button>
        </div>
        <p className="text-xs text-muted leading-6">{s.measureHint}</p>
        {data?.storedUpdatedAt && (
          <p className="text-xs text-muted">{s.lastSaved(f.date(data.storedUpdatedAt), f.time(data.storedUpdatedAt))}</p>
        )}
      </div>

      {!loading && data && data.rows.length > 0 && data.measuredAt && (
        <p className="text-xs text-muted">{s.measuredAt(f.date(data.measuredAt), f.time(data.measuredAt))}</p>
      )}

      {/* ── Staleness — honoured by _router_model as-is, but the admin deserves to know ── */}
      {!loading && data && data.rows.length > 0 && stale && data.measuredAt && (
        <div
          className="flex items-start gap-2"
          style={{ padding: '0.85rem 1rem', borderRadius: 'var(--radius-md)', background: 'var(--warning-dim, rgba(234,179,8,.12))', border: '1px solid var(--warning, #eab308)' }}
        >
          <Icon name="warning" size={16} className="text-[var(--warning,#eab308)] shrink-0 mt-0.5" />
          <p className="text-xs" style={{ color: 'var(--warning, #eab308)' }}>
            {s.staleWarning(f.date(data.measuredAt), f.time(data.measuredAt))}
          </p>
        </div>
      )}

      {!loading && loadError && (
        <div
          className="flex items-center justify-between gap-3"
          style={{ padding: '0.85rem 1rem', borderRadius: 'var(--radius-md)', background: 'var(--danger-dim)', border: '1px solid var(--danger)' }}
        >
          <p className="text-xs" style={{ color: 'var(--danger)' }}>{s.loadErrorToast}</p>
          <button className="btn btn-sm" onClick={load}>
            <Icon name="refresh" size={14} />
            {s.retry}
          </button>
        </div>
      )}

      {!loading && data && data.rows.length > 0 && (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
          <StatCard icon="check" label={s.statEligible} value={f.num(eligibleCount)} color="var(--success, #22c55e)" />
          <StatCard icon="close" label={s.statPermanent} value={f.num(permanentCount)} color="var(--danger, #ef4444)" />
          <StatCard icon="clock" label={s.statTransient} value={f.num(transientCount)} color="var(--warning, #eab308)" />
        </div>
      )}

      <div className="admin-card">
        {loading ? (
          <div className="p-6 text-center text-sm text-muted">{s.loading}</div>
        ) : !data ? (
          <div className="p-6 text-center text-sm text-muted">{s.noData}</div>
        ) : data.neverMeasured ? (
          <div
            style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', padding: '1.25rem 1rem', borderRadius: 'var(--radius-md)', background: 'var(--bg-hover)' }}
          >
            <p className="text-sm text-primary" style={{ fontWeight: 600 }}>{s.neverMeasuredTitle}</p>
            <p className="text-xs text-muted leading-6">{s.neverMeasuredBody}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="p-3">{s.colModel}</th>
                  <th className="p-3">{s.colState}</th>
                  <th className="p-3">{s.colReason}</th>
                  <th className="p-3">{s.colRetryAfter}</th>
                  <th className="p-3">{s.colLastRecorded}</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r: RouterProbeRow) => {
                  const badge = stateBadgeStyle(r.state)
                  return (
                    <tr key={r.publicId}>
                      <td className="p-3 font-mono text-xs text-primary" dir="ltr">{r.publicId}</td>
                      <td className="p-3">
                        <span className="text-xs px-2 py-1 rounded-full" style={badge}>{stateLabel(r.state, s)}</span>
                      </td>
                      <td className="p-3 text-xs text-secondary">
                        {reasonLabel(r.reason, s)}
                        {r.state === 'ineligiblePermanent' && r.sampleReply && (
                          <div className="text-xs text-muted mt-1" dir="ltr">{s.sampleReplyLabel}: {r.sampleReply}</div>
                        )}
                      </td>
                      <td className="p-3 text-xs">
                        {r.state === 'ineligibleTransient' && r.retryAfter
                          ? `${f.date(r.retryAfter)} — ${f.time(r.retryAfter)}`
                          : s.noRetry}
                      </td>
                      <td className="p-3 text-xs">{r.at ? `${f.date(r.at)} — ${f.time(r.at)}` : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
