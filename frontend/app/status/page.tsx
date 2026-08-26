'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { Skeleton } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt, type Formatters } from '@/lib/i18n'
import { HEALTH_TONE, healthLabel } from '@/app/chat/components/modelUtils'
import type { HealthStatus, HealthSummary, ModelHealthEntry } from '@/types/catalog'
import { useStatusSummary, StatusOverviewSections, SupportSection } from './StatusSections'
import { statusPageStrings } from './page.strings'

type Strings = ReturnType<typeof statusPageStrings>

/* ═══════════════════════════════════════════════════════════════════════════
   Live model status.

   Reads GET /api/models/health, which the backend recomputes from a rolling
   window of probe and real-traffic samples. Nothing here is hard-coded: if a
   model is missing from this page it is missing from the catalog.
   ═══════════════════════════════════════════════════════════════════════════ */

const REFRESH_MS = 30_000

const STATUS_ORDER: HealthStatus[] = ['down', 'degraded', 'unknown', 'healthy']

const OVERALL_TONE: Record<HealthSummary['overall'], string> = {
  operational: 'var(--positive)',
  degraded: 'var(--warning)',
  down: 'var(--danger)',
}

const GATEWAY_DOT: Record<NonNullable<HealthSummary['gateways']>['status'], string> = {
  operational: 'var(--positive)',
  degraded: 'var(--warning)',
  down: 'var(--danger)',
  unknown: 'var(--muted, #8b8b8b)',
}

/** Thin wrapper: this page always rounds before formatting. */
function num(f: Formatters, n: number | null | undefined, fallback = '—'): string {
  if (n == null || Number.isNaN(n)) return fallback
  return f.num(Math.round(n), { fallback })
}

function relativeTime(iso: string | null, f: Formatters, s: Strings): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return s.justNow
  if (seconds < 3600) return s.minutesAgo(num(f, seconds / 60))
  if (seconds < 86_400) return s.hoursAgo(num(f, seconds / 3600))
  return s.daysAgo(num(f, seconds / 86_400))
}

function StatusRow({
  model,
  f,
  s,
  health,
}: {
  model: ModelHealthEntry
  f: Formatters
  s: Strings
  health: Record<HealthStatus, string>
}) {
  return (
    <tr className="status-row">
      <td data-label={s.colModel} data-col="model">
        <div className="status-model">
          <span
            className="model-health-dot"
            style={{ background: HEALTH_TONE[model.status] }}
            aria-hidden
          />
          <div className="status-model-text">
            <span className="status-model-name" dir="ltr">
              {model.displayName}
            </span>
            {model.displayName !== model.id && (
              <span className="status-model-id" dir="ltr">
                {model.id}
              </span>
            )}
          </div>
        </div>
      </td>
      <td data-label={s.colStatus}>
        <span className={`model-health-badge model-health-${model.status}`}>
          {health[model.status]}
        </span>
      </td>
      <td className="status-num" data-label={s.colSuccessRate}>
        {model.successRate == null ? '—' : f.percent(model.successRate * 100)}
      </td>
      <td className="status-num" data-label={s.colLatency}>
        {model.latencyP50Ms == null ? (
          '—'
        ) : (
          // dir="ltr" so the unit stays after the number; the RTL paragraph
          // otherwise reorders it to "ms ۷۸۰".
          <span dir="ltr">{num(f, model.latencyP50Ms)} ms</span>
        )}
      </td>
      <td className="status-num" data-label={s.colSamples}>{num(f, model.sampleCount, f.num(0))}</td>
      <td data-label={s.colLastEvent}>
        {model.status === 'healthy' || !model.lastError ? (
          <span className="status-muted">{relativeTime(model.lastOkAt, f, s)}</span>
        ) : (
          <span className="status-error" dir="ltr" title={model.lastError}>
            {model.lastError}
          </span>
        )}
      </td>
    </tr>
  )
}

export default function StatusPage() {
  const lang = useLang()
  const f = fmt(lang)
  const s = statusPageStrings(lang)
  const health = healthLabel(lang)
  const [data, setData] = useState<HealthSummary | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)
  const summary = useStatusSummary()

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/models/health', { cache: 'no-store' })
      if (!res.ok) throw new Error(String(res.status))
      setData(await res.json())
      setError(false)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, REFRESH_MS)
    // Refresh immediately when the tab comes back rather than showing stale
    // numbers on a page whose whole point is being current.
    const onVisible = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [load])

  const models = useMemo(() => {
    if (!data) return []
    // Problems first — someone opening this page is usually looking for what
    // is broken, not scrolling an alphabetical list to find it.
    return [...data.models].sort((a, b) => {
      const byStatus = STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status)
      if (byStatus !== 0) return byStatus
      return a.displayName.localeCompare(b.displayName)
    })
  }, [data])

  const overallTone = data ? OVERALL_TONE[data.overall] : null
  const overallLabel = data ? s.overall[data.overall] : null

  return (
    <div className="status-page">
      <header className="status-header">
        <div>
          <h1 className="page-title">{s.title}</h1>
          <p className="page-subtitle">
            {s.subtitle}
            {data && s.subtitleWindow(f.num(data.windowMinutes))}
          </p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
          <Icon name="refresh" size={14} />
          {s.refresh}
        </button>
      </header>

      <StatusOverviewSections summary={summary} />

      {loading && (
        <div className="card status-skeletons">
          <Skeleton className="h-8 w-1/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-32" />
        </div>
      )}

      {!loading && error && (
        <div className="card status-error-card">
          <Icon name="warning" size={20} />
          <div>
            <strong>{s.unavailableTitle}</strong>
            <p className="card-desc">{s.unavailableDesc}</p>
          </div>
        </div>
      )}

      {!loading && !error && data && overallTone && overallLabel && (
        <>
          <div className="card status-banner" style={{ borderColor: overallTone }}>
            <span
              className="model-health-dot status-banner-dot"
              style={{ background: overallTone }}
              aria-hidden
            />
            <div>
              <strong style={{ color: overallTone }}>{overallLabel}</strong>
              {/* Separate elements rather than a "·" between each pair: in RTL
                  a middle dot sits right against the preceding digit, so
                  "۱ ناپایدار · ۱ down" renders as though it read "۱۰". */}
              <p className="card-desc status-counts">
                {STATUS_ORDER.map((st) => (
                  <span key={st} className="status-count">
                    <span className="status-count-value">{f.num(data.counts[st])}</span>
                    {health[st]}
                  </span>
                ))}
              </p>
            </div>
          </div>

          {/* Model supply, as ONE aggregate.
              This section used to list each upstream gateway by name with its
              own latency -- on an anonymous page, which published the supply
              chain to every visitor. A normal user never learns which
              upstream serves anything; the named breakdown lives in the admin
              panel only. What remains is the part a visitor can act on: when
              supply is degraded, every model behind it reads as broken, and
              the page should say so without naming anything. */}
          {data.gateways && (
            <section className="status-section">
              <h2 className="aurora-section-title">{s.supplySection}</h2>
              <div className="status-upstreams">
                <div className="card status-upstream">
                  <span
                    className="model-health-dot"
                    style={{ background: GATEWAY_DOT[data.gateways.status] }}
                    aria-hidden
                  />
                  <div className="status-upstream-text">
                    <span className="status-model-name">
                      {s.gateway[data.gateways.status].label}
                    </span>
                    <span className="status-muted">
                      {s.gateway[data.gateways.status].hint}
                    </span>
                  </div>
                </div>
              </div>
            </section>
          )}

          <section className="status-section">
            <h2 className="aurora-section-title">{s.modelsSection}</h2>
            <div className="card status-table-wrap">
              <table className="status-table">
                <thead>
                  <tr>
                    <th>{s.colModel}</th>
                    <th>{s.colStatus}</th>
                    <th>{s.colSuccessRate}</th>
                    <th>{s.colLatency}</th>
                    <th>{s.colSamples}</th>
                    <th>{s.colLastEvent}</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m) => (
                    <StatusRow key={m.id} model={m} f={f} s={s} health={health} />
                  ))}
                </tbody>
              </table>

              {models.length === 0 && <p className="status-empty">{s.noSamples}</p>}
            </div>
          </section>

          <p className="status-footnote">
            {s.footnote(relativeTime(data.generatedAt, f, s), f.num(REFRESH_MS / 1000))}
          </p>
        </>
      )}

      <SupportSection summary={summary} />
    </div>
  )
}
