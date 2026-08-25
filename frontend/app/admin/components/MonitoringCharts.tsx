'use client'

import { useLang, type Lang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/adminI18n'
import { toFaDigits } from '@/lib/format'
import { monitoringChartsStrings } from './MonitoringCharts.strings'

// ═══════════════════════════════════════════════════════════════════════════
// Pure presentational chart primitives for the admin monitoring tab.
//
// recharts is FORBIDDEN — it breaks the production build (see AdminCharts.tsx
// stub). Everything here is hand-written div-bars / inline <svg>, matching the
// failed-login sparkline pattern in AdminPanel.tsx.
// ═══════════════════════════════════════════════════════════════════════════

export type TrafficHour = {
  hour: string
  total: number
  errors: number
  p50Ms: number | null
  p95Ms: number | null
}

export type VolumeDay = {
  day: string
  requests: number
  revenue: number
}

function Empty() {
  const lang = useLang()
  const s = monitoringChartsStrings(lang)
  return (
    <div className="text-center text-[var(--text-muted)] py-8 text-sm">{s.empty}</div>
  )
}

/** Short hour label from an ISO datetime string, e.g. "۱۴:۰۰" / "14:00". */
function hourLabel(iso: string, lang: Lang): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const f = fmt(lang)
  return `${f.num(d.getHours())}:${monitoringChartsStrings(lang).minutesZero}`
}

/** Short day label from an ISO datetime string, e.g. "۲۱ مرداد" / "21 Aug". */
function dayLabel(iso: string, lang: Lang): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  if (lang === 'en') {
    return d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric' })
  }
  // toFaDigits is lib/format's own normaliser -- Intl returns Latin digits
  // under the small-icu build the production Node image uses, and this is the
  // one helper that already knows that. A second copy of the digit table
  // (this file had one) is exactly the drift lib/format exists to prevent.
  return toFaDigits(d.toLocaleDateString('fa-IR', { month: 'short', day: 'numeric' }))
}

// ─── TrafficBars ─────────────────────────────────────────────────────────

export function TrafficBars({ hours }: { hours: TrafficHour[] }) {
  const lang = useLang()
  const s = monitoringChartsStrings(lang)
  const f = fmt(lang)
  if (!hours || hours.length === 0) return <Empty />

  const max = Math.max(...hours.map((h) => h.total), 0)

  return (
    <div dir="ltr">
      <div className="flex items-end gap-1 h-24">
        {hours.map((h, i) => {
          const totalPct = max > 0 ? (h.total / max) * 100 : 0
          const errorPct = max > 0 ? (h.errors / max) * 100 : 0
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1">
              <div
                className="w-full rounded-t transition-all duration-300 relative overflow-hidden"
                style={{
                  height: `${Math.max(totalPct, h.total > 0 ? 4 : 0)}%`,
                  background: 'var(--accent)',
                  opacity: 0.8,
                }}
                title={s.trafficTooltip(h.hour, f.num(h.total), f.num(h.errors))}
              >
                {h.errors > 0 && (
                  <div
                    className="absolute bottom-0 left-0 w-full"
                    style={{
                      height: max > 0 ? `${(errorPct / totalPct) * 100 || 100}%` : 0,
                      background: 'var(--danger)',
                    }}
                  />
                )}
              </div>
            </div>
          )
        })}
      </div>
      <div className="flex justify-between mt-2">
        <span className="text-[10px] text-[var(--text-muted)]">{hourLabel(hours[0].hour, lang)}</span>
        <span className="text-[10px] text-[var(--text-muted)]">
          {hourLabel(hours[hours.length - 1].hour, lang)}
        </span>
      </div>
    </div>
  )
}

// ─── LatencyChart ────────────────────────────────────────────────────────

const SVG_W = 600
const SVG_H = 120

/** Builds a polyline `points` string, skipping (breaking the line at) nulls. */
function buildSegments(hours: TrafficHour[], pick: (h: TrafficHour) => number | null): string[] {
  const values = hours.map(pick)
  const finite = values.filter((v): v is number => v != null && Number.isFinite(v))
  if (finite.length === 0) return []

  const max = Math.max(...finite, 1)
  const min = Math.min(...finite, 0)
  const range = max - min || 1
  const stepX = hours.length > 1 ? SVG_W / (hours.length - 1) : 0

  const segments: string[] = []
  let current: string[] = []

  values.forEach((v, i) => {
    if (v == null || !Number.isFinite(v)) {
      if (current.length > 0) {
        segments.push(current.join(' '))
        current = []
      }
      return
    }
    const x = hours.length > 1 ? i * stepX : SVG_W / 2
    const y = SVG_H - ((v - min) / range) * SVG_H
    current.push(`${x},${y}`)
  })
  if (current.length > 0) segments.push(current.join(' '))

  return segments
}

export function LatencyChart({ hours }: { hours: TrafficHour[] }) {
  if (!hours || hours.length === 0) return <Empty />

  const p50Segments = buildSegments(hours, (h) => h.p50Ms)
  const p95Segments = buildSegments(hours, (h) => h.p95Ms)

  if (p50Segments.length === 0 && p95Segments.length === 0) return <Empty />

  return (
    <div dir="ltr">
      <div className="flex items-center gap-4 mb-2 text-[10px] text-[var(--text-muted)]">
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-2.5 h-2.5 rounded-sm"
            style={{ background: 'var(--accent)' }}
          />
          p50
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-2.5 h-2.5 rounded-sm"
            style={{ background: 'var(--warning)' }}
          />
          p95
        </span>
      </div>
      <svg
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        preserveAspectRatio="none"
        style={{ width: '100%', height: '120px', display: 'block' }}
      >
        {p95Segments.map((points, i) => (
          <polyline
            key={`p95-${i}`}
            points={points}
            fill="none"
            stroke="var(--warning)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {p50Segments.map((points, i) => (
          <polyline
            key={`p50-${i}`}
            points={points}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
    </div>
  )
}

// ─── VolumeBars ──────────────────────────────────────────────────────────

export function VolumeBars({ days }: { days: VolumeDay[] }) {
  const lang = useLang()
  const s = monitoringChartsStrings(lang)
  const f = fmt(lang)
  if (!days || days.length === 0) return <Empty />

  const recent = days.slice(-7)
  const max = Math.max(...recent.map((d) => d.requests), 0)

  return (
    <div dir="ltr">
      <div className="flex items-end gap-2 h-24">
        {recent.map((d, i) => {
          const pct = max > 0 ? (d.requests / max) * 100 : 0
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1">
              <div
                className="w-full rounded-t transition-all duration-300"
                style={{
                  height: `${Math.max(pct, d.requests > 0 ? 4 : 0)}%`,
                  background: 'var(--positive)',
                  opacity: 0.8,
                }}
                title={s.volumeTooltip(d.day, f.num(d.requests), f.price(d.revenue))}
              />
              <span className="text-[10px] text-[var(--text-muted)]">{f.num(d.requests)}</span>
            </div>
          )
        })}
      </div>
      <div className="flex justify-between mt-2">
        <span className="text-[10px] text-[var(--text-muted)]">{dayLabel(recent[0].day, lang)}</span>
        <span className="text-[10px] text-[var(--text-muted)]">
          {dayLabel(recent[recent.length - 1].day, lang)}
        </span>
      </div>
    </div>
  )
}
