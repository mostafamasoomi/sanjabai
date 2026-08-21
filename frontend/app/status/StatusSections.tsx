'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════════════════
   Overview sections for the public /status page: incident banner, per-service
   uptime cards (fed by the Kuma-backed GET /status/summary), and a support
   contact block. Kept separate from page.tsx (which renders live model
   health) because the two data sources refresh independently.
   ═══════════════════════════════════════════════════════════════════════════ */

const REFRESH_MS = 60_000

export type StatusServiceKey = 'web' | 'api' | 'gateway'
export type StatusServiceStatus = 'up' | 'down' | 'unknown'

export type StatusBeat = {
  t: string | null
  ok: boolean
  pingMs: number | null
}

export type StatusService = {
  key: StatusServiceKey | string
  label: string
  status: StatusServiceStatus
  uptime24h: number | null
  avgPingMs: number | null
  beats: StatusBeat[]
}

export type StatusIncidentSeverity = 'info' | 'warning' | 'critical'

export type StatusIncident = {
  title: string
  body: string
  severity: StatusIncidentSeverity
  startedAt: string
}

export type StatusSupport = {
  email: string | null
  telegram: string | null
}

export type StatusSummary = {
  services: StatusService[]
  monitoringUp: boolean
  stale: boolean
  incident: StatusIncident | null
  /** Optional: the backend field may not be deployed yet. */
  support?: StatusSupport | null
  generatedAt: string
}

/** Thin wrapper: this file always rounds before formatting. */
function fa(n: number | null | undefined, fallback = '—'): string {
  if (n == null || Number.isNaN(n)) return fallback
  return faNum(Math.round(n), { fallback })
}

function relativeTime(iso: string | null): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return 'همین الان'
  if (seconds < 3600) return `${fa(seconds / 60)} دقیقه پیش`
  if (seconds < 86_400) return `${fa(seconds / 3600)} ساعت پیش`
  return `${fa(seconds / 86_400)} روز پیش`
}

/** Kuma's uptime24h is a 0..1 fraction, but be defensive in case that ever
 * changes upstream to an already-percent number. */
function uptimePercent(value: number | null): string {
  if (value == null || Number.isNaN(value)) return '—'
  const pct = value > 1 ? value : value * 100
  const clamped = Math.min(100, Math.max(0, pct))
  return `${fa(clamped)}٪`
}

const SEVERITY_COLOR: Record<StatusIncidentSeverity, string> = {
  info: 'var(--info)',
  warning: 'var(--warning)',
  critical: 'var(--danger)',
}

const STATUS_DOT_COLOR: Record<StatusServiceStatus, string> = {
  up: 'var(--positive)',
  down: 'var(--danger)',
  unknown: 'var(--text-dim)',
}

export function useStatusSummary(): {
  data: StatusSummary | null
  loading: boolean
  error: boolean
  reload: () => void
} {
  const [data, setData] = useState<StatusSummary | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/status/summary', { cache: 'no-store' })
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
    const onVisible = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [load])

  return { data, loading, error, reload: load }
}

function IncidentBanner({ incident }: { incident: StatusIncident }) {
  const color = SEVERITY_COLOR[incident.severity] || SEVERITY_COLOR.warning
  return (
    <div
      className="card"
      style={{ borderRight: `3px solid ${color}`, borderTop: `1px solid ${color}` }}
    >
      <strong style={{ color }}>{incident.title}</strong>
      <p className="card-desc">{incident.body}</p>
      <p className="status-muted" style={{ marginTop: '0.3rem' }}>
        شروع: {relativeTime(incident.startedAt)}
      </p>
    </div>
  )
}

function BeatBar({ beats }: { beats: StatusBeat[] }) {
  if (!beats || beats.length === 0) return null
  return (
    <div dir="ltr" style={{ display: 'flex', gap: '2px', marginTop: '0.5rem' }}>
      {beats.map((b, i) => {
        const title = `${b.t ?? '—'}${b.pingMs != null ? ` · ${fa(b.pingMs)} ms` : ''}`
        return (
          <div
            key={i}
            title={title}
            style={{
              flex: 1,
              height: '1.1rem',
              minWidth: '3px',
              borderRadius: '2px',
              background: b.ok ? 'var(--positive)' : 'var(--danger)',
            }}
          />
        )
      })}
    </div>
  )
}

function ServiceCard({ service }: { service: StatusService }) {
  return (
    <div className="card status-upstream" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <span
          className="model-health-dot"
          style={{ background: STATUS_DOT_COLOR[service.status] || STATUS_DOT_COLOR.unknown }}
          aria-hidden
        />
        <div className="status-upstream-text">
          <span className="status-model-name">{service.label}</span>
          <span className="status-muted">
            <span dir="ltr">
              {uptimePercent(service.uptime24h)}
              {service.avgPingMs != null && ` · ${fa(service.avgPingMs)} ms`}
            </span>
          </span>
        </div>
      </div>
      <BeatBar beats={service.beats} />
    </div>
  )
}

export function StatusOverviewSections({
  summary,
}: {
  summary: ReturnType<typeof useStatusSummary>
}) {
  const { data, loading } = summary

  const showEmptyNotice = useMemo(() => {
    if (!data) return false
    return !data.monitoringUp || data.services.length === 0
  }, [data])

  if (loading && !data) {
    return (
      <div className="card status-skeletons">
        <div className="skeleton h-8 w-1/3" />
        <div className="skeleton h-4 w-1/2" />
      </div>
    )
  }

  if (!data) return <></>

  return (
    <>
      {data.incident && <IncidentBanner incident={data.incident} />}

      <section className="status-section">
        <h2 className="aurora-section-title">وضعیت سرویس‌ها</h2>

        {showEmptyNotice ? (
          <div className="card status-upstream">
            <span className="status-muted">پایش بیرونی در دسترس نیست</span>
          </div>
        ) : (
          <div className="status-upstreams">
            {data.services.map((s) => (
              <ServiceCard key={s.key} service={s} />
            ))}
          </div>
        )}

        {data.stale && (
          <p className="status-muted" style={{ marginTop: '0.3rem' }}>
            داده‌ها ممکن است به‌روز نباشند
          </p>
        )}
      </section>
    </>
  )
}

export function SupportSection({
  summary,
}: {
  summary: ReturnType<typeof useStatusSummary>
}) {
  const email = summary.data?.support?.email
  if (!email) return null

  const telegram = summary.data?.support?.telegram
  const telegramHandle = telegram ? telegram.replace(/^@/, '') : null

  return (
    <section className="status-section">
      <h2 className="aurora-section-title">پشتیبانی</h2>
      <div className="card">
        <p className="card-desc">در صورت مشاهده‌ی اختلال یا سوال، از راه‌های زیر با ما در تماس باشید.</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.5rem' }}>
          <a href={`mailto:${email}`} className="auth-inline-link" style={{ display: 'inline-flex', gap: '0.4rem', alignItems: 'center' }}>
            <Icon name="mail" size={14} />
            <span dir="ltr">{email}</span>
          </a>
          {telegramHandle && (
            <a
              href={`https://t.me/${telegramHandle}`}
              target="_blank"
              rel="noopener noreferrer"
              className="auth-inline-link"
              style={{ display: 'inline-flex', gap: '0.4rem', alignItems: 'center' }}
            >
              <Icon name="send" size={14} />
              <span dir="ltr">@{telegramHandle}</span>
            </a>
          )}
        </div>
      </div>
    </section>
  )
}
