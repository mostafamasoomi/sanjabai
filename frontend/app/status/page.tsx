'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { Skeleton } from '@/components/ui'
import { faNum } from '@/lib/format'
import { HEALTH_LABEL, HEALTH_TONE } from '@/app/chat/components/modelUtils'
import type { HealthStatus, HealthSummary, ModelHealthEntry } from '@/types/catalog'

/* ═══════════════════════════════════════════════════════════════════════════
   Live model status.

   Reads GET /api/models/health, which the backend recomputes from a rolling
   window of probe and real-traffic samples. Nothing here is hard-coded: if a
   model is missing from this page it is missing from the catalog.
   ═══════════════════════════════════════════════════════════════════════════ */

const REFRESH_MS = 30_000

const OVERALL_COPY: Record<HealthSummary['overall'], { label: string; tone: string }> = {
  operational: { label: 'همه‌ی سرویس‌ها فعال هستند', tone: 'var(--positive)' },
  degraded: { label: 'بخشی از مدل‌ها ناپایدار هستند', tone: 'var(--warning)' },
  down: { label: 'اختلال گسترده', tone: 'var(--danger)' },
}

const STATUS_ORDER: HealthStatus[] = ['down', 'degraded', 'unknown', 'healthy']

/** Thin wrapper: this page always rounds before formatting. */
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

function StatusRow({ model }: { model: ModelHealthEntry }) {
  return (
    <tr className="status-row">
      <td data-label="مدل">
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
      <td data-label="وضعیت">
        <span className={`model-health-badge model-health-${model.status}`}>
          {HEALTH_LABEL[model.status]}
        </span>
      </td>
      <td className="status-num" data-label="نرخ موفقیت">
        {model.successRate == null ? '—' : `${fa(model.successRate * 100)}٪`}
      </td>
      <td className="status-num" data-label="تأخیر میانه">
        {model.latencyP50Ms == null ? (
          '—'
        ) : (
          // dir="ltr" so the unit stays after the number; the RTL paragraph
          // otherwise reorders it to "ms ۷۸۰".
          <span dir="ltr">{fa(model.latencyP50Ms)} ms</span>
        )}
      </td>
      <td className="status-num" data-label="نمونه">{fa(model.sampleCount, '۰')}</td>
      <td data-label="آخرین رویداد">
        {model.status === 'healthy' || !model.lastError ? (
          <span className="status-muted">{relativeTime(model.lastOkAt)}</span>
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
  const [data, setData] = useState<HealthSummary | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)

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

  const overall = data ? OVERALL_COPY[data.overall] : null

  return (
    <div className="status-page">
      <header className="status-header">
        <div>
          <h1 className="page-title">وضعیت مدل‌ها</h1>
          <p className="page-subtitle">
            سلامت هر مدل به‌صورت زنده اندازه‌گیری می‌شود — از درخواست‌های واقعی کاربران و
            بررسی‌های دوره‌ای.
            {data && ` بازه‌ی محاسبه: ${fa(data.windowMinutes)} دقیقه‌ی گذشته.`}
          </p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
          <Icon name="refresh" size={14} />
          به‌روزرسانی
        </button>
      </header>

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
            <strong>وضعیت در دسترس نیست</strong>
            <p className="card-desc">
              گزارش سلامت خوانده نشد. این یعنی خود سرویس وضعیت مشکل دارد، نه لزوماً
              مدل‌ها.
            </p>
          </div>
        </div>
      )}

      {!loading && !error && data && overall && (
        <>
          <div className="card status-banner" style={{ borderColor: overall.tone }}>
            <span
              className="model-health-dot status-banner-dot"
              style={{ background: overall.tone }}
              aria-hidden
            />
            <div>
              <strong style={{ color: overall.tone }}>{overall.label}</strong>
              {/* Separate elements rather than a "·" between each pair: in RTL
                  a middle dot sits right against the preceding digit, so
                  "۱ ناپایدار · ۱ down" renders as though it read "۱۰". */}
              <p className="card-desc status-counts">
                {STATUS_ORDER.map((s) => (
                  <span key={s} className="status-count">
                    <span className="status-count-value">{fa(data.counts[s])}</span>
                    {HEALTH_LABEL[s]}
                  </span>
                ))}
              </p>
            </div>
          </div>

          {/* Upstream gateways. When one of these is down every model behind it
              reads as broken, so it is worth calling out separately. */}
          <section className="status-section">
            <h2 className="aurora-section-title">درگاه‌های بالادست</h2>
            <div className="status-upstreams">
              {data.upstreams.map((u) => (
                <div key={u.name} className="card status-upstream">
                  <span
                    className="model-health-dot"
                    style={{ background: u.ok ? 'var(--positive)' : 'var(--danger)' }}
                    aria-hidden
                  />
                  <div className="status-upstream-text">
                    <span className="status-model-name" dir="ltr">
                      {u.name}
                    </span>
                    <span className="status-muted">
                      {u.ok ? (
                        <span dir="ltr">{fa(u.latencyMs)} ms</span>
                      ) : (
                        u.error || 'در دسترس نیست'
                      )}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="status-section">
            <h2 className="aurora-section-title">مدل‌ها</h2>
            <div className="card status-table-wrap">
              <table className="status-table">
                <thead>
                  <tr>
                    <th>مدل</th>
                    <th>وضعیت</th>
                    <th>نرخ موفقیت</th>
                    <th>تأخیر میانه</th>
                    <th>نمونه</th>
                    <th>آخرین رویداد</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m) => (
                    <StatusRow key={m.id} model={m} />
                  ))}
                </tbody>
              </table>

              {models.length === 0 && (
                <p className="status-empty">
                  هنوز نمونه‌ای ثبت نشده است. اولین بررسی دوره‌ای پس از راه‌اندازی سرویس
                  انجام می‌شود.
                </p>
              )}
            </div>
          </section>

          <p className="status-footnote">
            آخرین به‌روزرسانی: {relativeTime(data.generatedAt)} · این صفحه هر{' '}
            {fa(REFRESH_MS / 1000)} ثانیه تازه می‌شود.
          </p>
        </>
      )}
    </div>
  )
}
