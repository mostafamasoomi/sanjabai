'use client'

import { Fragment, useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faDate, faTime } from '@/lib/format'
import { SectionHeader, StatCard } from './shared'
import {
  parseOverheadResponse,
  elapsedParts,
  type ParsedOverhead,
} from './upstreamOverheadHelpers'

/* ═══════════════════════════════════════════════════════════════════════════
   Upstream overhead — measured live on production 2026-08-23: the ninerouter
   upstream injects a preamble the user never wrote into the prompt it sends
   the model. The same 2-token "سلام" costs a wildly different number of
   prompt tokens depending on which upstream route serves it, and the user
   currently pays for all of it. This section lets an admin see the stored
   overhead-per-route map and trigger a live re-measurement.

   Self-contained (fetches via the `api` helper AdminPanel already exposes),
   same pattern as ./MarkupSection.tsx and ./ExchangeRateSection.tsx.

   Server contract — pinned against backend/admin_overhead.py (read directly,
   not guessed):
     GET  /admin/upstream-overhead          -> { stored: { version,
                                                measured_at, entries,
                                                provider_default,
                                                measurements? },
                                                storedUpdatedAt,
                                                perProviderStats7d }
     POST /admin/upstream-overhead/measure  -> re-measures live (slow, real
                                                upstream requests — allow at
                                                least 60s) and returns the
                                                same shape.

   `stored.entries["<upstream>:<prefix>"]` is the overhead a specifically
   measured route is actually charged. `stored.provider_default["<upstream>"]`
   is a SEPARATE fallback used at billing time for any prefix that was not
   measured — rendered as its own table below, never merged into the entries
   table, so a fallback number can never be mistaken for a direct
   measurement. `perProviderStats7d` is keyed by provider, not by route
   (several routes can share one provider's stats row), so it is its own
   table too rather than a column on each route row.

   The normalizer (parseOverheadResponse, ./upstreamOverheadHelpers.ts)
   validates strictly against that one real shape and THROWS on anything
   that doesn't match, rather than degrading quietly to an empty table —
   this table decides what every user is charged, so "the backend response
   is malformed" must render as a visibly different state from "nothing has
   been measured yet" (the actual shipped-default inert state). See that
   file's header for the full reasoning.

   The parser and the elapsed-time math live in ./upstreamOverheadHelpers.ts
   rather than here, purely so they're unit-testable: Vitest here has no
   vite-react-plugin and tsconfig.json sets `jsx: preserve`, so it cannot
   parse any `.tsx` file at all (including this one), the same reason
   ./apiError.ts was already split out of AdminPanel.tsx.
   ═══════════════════════════════════════════════════════════════════════════ */

interface UpstreamOverheadSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

/** `۴۲ ثانیه` under a minute, `۱ دقیقه و ۵ ثانیه` past it — so a 40s
 *  measurement reads as "still going" rather than looking hung. Digits go
 *  through `faNum` (the math itself lives in elapsedParts, see the import
 *  above) — this is the one place in the app allowed to render a number. */
function formatElapsedSeconds(ms: number): string {
  const { minutes, seconds } = elapsedParts(ms)
  if (minutes === 0) return `${faNum(seconds)} ثانیه`
  return seconds === 0 ? `${faNum(minutes)} دقیقه` : `${faNum(minutes)} دقیقه و ${faNum(seconds)} ثانیه`
}

export default function UpstreamOverheadSection({ api }: UpstreamOverheadSectionProps) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<ParsedOverhead | null>(null)
  // Distinct from a plain fetch failure: the request succeeded but the body
  // did not match the real backend contract — must never look like "no
  // data yet" (see the header comment above).
  const [parseError, setParseError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const [measuring, setMeasuring] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)
  const measureStart = useRef<number | null>(null)

  const load = async () => {
    setLoading(true)
    setParseError(null)
    try {
      const res = await api('/api/admin/upstream-overhead')
      const body = await res.json()
      setData(parseOverheadResponse(body))
    } catch (err) {
      setData(null)
      setParseError(err instanceof Error ? err.message : 'خطا در دریافت اطلاعات سربار پروایدرها')
      toast('خطا در دریافت اطلاعات سربار پروایدرها', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
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
    setMeasuring(true)
    setElapsedMs(0)
    measureStart.current = Date.now()
    try {
      const res = await api('/api/admin/upstream-overhead/measure', { method: 'POST' })
      const body = await res.json()
      // measure_upstream_overhead returns {status, measured, skipped, value}
      // where `value` is shaped like GET's `stored` (NOT the full
      // {stored, storedUpdatedAt, perProviderStats7d} envelope — it doesn't
      // carry storedUpdatedAt or perProviderStats7d at all, since those come
      // from a separate DB read GET does and this route doesn't repeat).
      // Re-fetching GET afterwards gets the canonical, complete view
      // (including the fresh 7-day stats and the new storedUpdatedAt)
      // instead of parsing two different response shapes.
      const measuredCount = typeof body?.measured === 'number' ? body.measured : null
      const skippedCount = Array.isArray(body?.skipped) ? body.skipped.length : null
      await load()
      toast(
        measuredCount != null
          ? `اندازه‌گیری زنده تمام شد — ${faNum(measuredCount)} مسیر اندازه‌گیری شد${
              skippedCount ? `، ${faNum(skippedCount)} مسیر رد شد` : ''
            }`
          : 'اندازه‌گیری زنده سربار به‌روزرسانی شد',
        'success',
      )
    } catch (err) {
      toast(err instanceof Error && err.message ? err.message : 'اندازه‌گیری سربار ناموفق بود', 'error')
    } finally {
      setMeasuring(false)
      measureStart.current = null
    }
  }

  const toggleExpanded = (routeKey: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(routeKey)) next.delete(routeKey)
      else next.add(routeKey)
      return next
    })
  }

  const totalRequests7d = data ? data.providerStats.reduce((sum, r) => sum + r.requests_7d, 0) : 0
  const totalTokensDiscounted7d = data ? data.providerStats.reduce((sum, r) => sum + r.tokens_discounted_7d, 0) : 0

  return (
    <div className="space-y-6">
      <SectionHeader
        title="سربار پروایدرهای بالادست"
        subtitle="مقدار توکنی که هر مسیر بالادست (بدون درخواست کاربر) به هر پیام اضافه می‌کند — کاربر امروز بابت همهٔ این توکن‌ها هزینه می‌دهد"
      />

      <div className="admin-card">
        <div className="flex items-center justify-between gap-4 flex-wrap mb-2">
          <h3 className="font-semibold text-sm text-primary">اندازه‌گیری زنده</h3>
          <button className="btn btn-sm" onClick={runMeasure} disabled={measuring}>
            {measuring ? (
              <>
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                <span>در حال اندازه‌گیری… ({formatElapsedSeconds(elapsedMs)})</span>
              </>
            ) : (
              <>
                <Icon name="refresh" size={14} />
                <span>اندازه‌گیری زنده</span>
              </>
            )}
          </button>
        </div>
        <p className="text-xs text-muted leading-6">
          این اندازه‌گیری درخواست واقعی به مسیرهای بالادست می‌زند و ممکن است بیش از یک دقیقه طول بکشد — تا پایان صبر کنید، قطع نشده.
        </p>
        {data?.storedUpdatedAt && (
          <p className="text-xs text-muted">
            آخرین ذخیره‌سازی: {faDate(data.storedUpdatedAt)} — {faTime(data.storedUpdatedAt)}
          </p>
        )}
      </div>

      {/* ── Malformed / unexpected response — deliberately distinct from the inert-empty state below ── */}
      {!loading && parseError && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '0.4rem',
            padding: '1rem 1.1rem',
            borderRadius: 'var(--radius-md)',
            background: 'var(--danger-dim)',
            border: '1px solid var(--danger)',
          }}
        >
          <div className="flex items-center gap-2">
            <Icon name="warning" size={16} className="text-[var(--danger)]" />
            <p className="text-sm" style={{ fontWeight: 700, color: 'var(--danger)' }}>
              پاسخ سرور با قرارداد مورد انتظار مطابقت ندارد
            </p>
          </div>
          <p className="text-xs" style={{ color: 'var(--danger)' }}>
            {parseError}
          </p>
          <p className="text-xs text-muted leading-6">
            این با «هنوز چیزی اندازه‌گیری نشده» فرق دارد — یعنی ساختار پاسخ backend عوض شده و این صفحه نمی‌تواند آن را بخواند. قبل از
            اعتماد به هر عددی در جدول زیر، این را برطرف کنید.
          </p>
          <button className="btn btn-sm" style={{ alignSelf: 'flex-start' }} onClick={load}>
            <Icon name="refresh" size={14} />
            تلاش دوباره
          </button>
        </div>
      )}

      {/* ── Stat summary — from perProviderStats7d, not per-route ── */}
      {!loading && data && data.providerStats.length > 0 && (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          <StatCard icon="compare" label="مسیرهای دارای اندازه‌گیری اختصاصی" value={faNum(data.entries.length)} color="var(--accent, #6366f1)" />
          <StatCard icon="chart" label="درخواست ۷ روز اخیر (مجموع پروایدرها)" value={faNum(totalRequests7d)} color="var(--warning, #eab308)" />
          <StatCard icon="cpu" label="توکن کسرشده ۷ روز اخیر (مجموع)" value={faNum(totalTokensDiscounted7d)} color="var(--success, #22c55e)" />
        </div>
      )}

      {/* ── Measured entries table ── */}
      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-1 text-primary">مسیرهای اندازه‌گیری‌شده — overhead اختصاصی</h3>
        <p className="text-xs text-muted mb-2">
          هر ردیف مستقیماً اندازه‌گیری شده — عدد سربار آن از پیش‌فرض هیچ پروایدری ارث نمی‌برد.
        </p>

        {loading ? (
          <div className="p-6 text-center text-sm text-muted">در حال بارگذاری…</div>
        ) : !data ? (
          <div className="p-6 text-center text-sm text-muted">اطلاعاتی در دسترس نیست</div>
        ) : data.isInert ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '0.4rem',
              padding: '1.25rem 1rem',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-hover)',
            }}
          >
            <p className="text-sm text-primary" style={{ fontWeight: 600 }}>
              نقشهٔ سربار هنوز خالی است — این حالت پیش‌فرض همان چیزی است که با آن منتشر شده‌ایم.
            </p>
            <p className="text-xs text-muted leading-6">
              یعنی کسر سربار هنوز غیرفعال است و فعلاً هیچ کاربری بابت سربار مسیر بالادست هزینهٔ اضافه نمی‌دهد. برای پر شدن این جدول و
              فعال شدن کسر واقعی، روی «اندازه‌گیری زنده» بزنید.
            </p>
          </div>
        ) : data.entries.length === 0 ? (
          <div className="p-6 text-center text-sm text-muted">
            آخرین اندازه‌گیری ({data.measuredAt ? `${faDate(data.measuredAt)} — ${faTime(data.measuredAt)}` : '—'}) هیچ مسیری را با موفقیت ثبت نکرد.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-right p-3">مسیر</th>
                  <th className="text-right p-3">پروایدر</th>
                  <th className="text-right p-3">سربار (توکن)</th>
                  <th className="text-right p-3">مدل نمونه</th>
                  <th className="text-right p-3">زمان اندازه‌گیری</th>
                  <th className="text-right p-3">جزئیات</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((r) => {
                  const isExpanded = expanded.has(r.route_key)
                  return (
                    <Fragment key={r.route_key}>
                      <tr>
                        <td className="p-3 font-mono text-xs text-primary">{r.route_key}</td>
                        <td className="p-3 text-xs">{r.provider}</td>
                        <td className="p-3">
                          <span className="badge">{faNum(r.overhead_tokens)}</span>
                        </td>
                        <td className="p-3 text-xs">{r.sample_model || '—'}</td>
                        <td className="p-3 text-xs">
                          {r.measured_at ? `${faDate(r.measured_at)} — ${faTime(r.measured_at)}` : '—'}
                        </td>
                        <td className="p-3">
                          <button className="btn btn-sm" onClick={() => toggleExpanded(r.route_key)} disabled={!r.has_measurement}>
                            <Icon name={isExpanded ? 'close' : 'search'} size={13} />
                            <span>{isExpanded ? 'بستن' : r.has_measurement ? 'نحوهٔ محاسبه' : 'بدون جزئیات'}</span>
                          </button>
                        </td>
                      </tr>
                      {isExpanded && r.has_measurement && (
                        <tr>
                          <td colSpan={6} className="p-3" style={{ background: 'var(--bg-hover)' }}>
                            <p className="text-xs text-muted mb-2">
                              اعداد خامی که سربار از روی آن‌ها محاسبه شده — یک عدد بدون این‌ها، یعنی معلوم نیست چرا مبلغ هر کاربر تغییر کرده.
                            </p>
                            <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))' }}>
                              <div><p className="text-xs text-muted mb-1">p۱</p><p className="text-sm text-primary font-mono">{r.p1 != null ? faNum(r.p1) : '—'}</p></div>
                              <div><p className="text-xs text-muted mb-1">p۲</p><p className="text-sm text-primary font-mono">{r.p2 != null ? faNum(r.p2) : '—'}</p></div>
                              <div><p className="text-xs text-muted mb-1">c۱</p><p className="text-sm text-primary font-mono">{r.c1 != null ? faNum(r.c1) : '—'}</p></div>
                              <div><p className="text-xs text-muted mb-1">c۲</p><p className="text-sm text-primary font-mono">{r.c2 != null ? faNum(r.c2) : '—'}</p></div>
                              <div><p className="text-xs text-muted mb-1">شیب (slope)</p><p className="text-sm text-primary font-mono">{r.slope != null ? faNum(r.slope, { decimals: 3 }) : '—'}</p></div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Provider-default fallback table — kept separate on purpose, see header comment ── */}
      {!loading && data && data.providerDefaults.length > 0 && (
        <div className="admin-card">
          <h3 className="font-semibold text-sm mb-1 text-primary">پیش‌فرض هر پروایدر — fallback برای مسیرهای اندازه‌گیری‌نشده</h3>
          <p className="text-xs text-muted mb-2">
            این عدد فقط برای پیشوندی از این پروایدر که در جدول بالا اندازه‌گیری اختصاصی ندارد اعمال می‌شود — با overhead اختصاصی هر مسیر یکی نیست.
          </p>
          <div className="overflow-x-auto">
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-right p-3">پروایدر</th>
                  <th className="text-right p-3">سربار پیش‌فرض (توکن)</th>
                </tr>
              </thead>
              <tbody>
                {data.providerDefaults.map((d) => (
                  <tr key={d.provider}>
                    <td className="p-3 text-xs">{d.provider}</td>
                    <td className="p-3">
                      <span className="badge">{faNum(d.overhead_tokens)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── 7-day per-provider stats — kept separate on purpose, see header comment ── */}
      {!loading && data && data.providerStats.length > 0 && (
        <div className="admin-card">
          <h3 className="font-semibold text-sm mb-1 text-primary">آمار ۷ روز اخیر به تفکیک پروایدر</h3>
          <p className="text-xs text-muted mb-2">
            این آمار به ازای پروایدر است، نه هر مسیر — چند مسیر می‌توانند یک ردیف آماری مشترک داشته باشند.
          </p>
          <div className="overflow-x-auto">
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-right p-3">پروایدر</th>
                  <th className="text-right p-3">درخواست ۷ روز</th>
                  <th className="text-right p-3">توکن کسرشده ۷ روز</th>
                </tr>
              </thead>
              <tbody>
                {data.providerStats.map((s) => (
                  <tr key={s.provider}>
                    <td className="p-3 text-xs">{s.provider}</td>
                    <td className="p-3 text-xs">{faNum(s.requests_7d)}</td>
                    <td className="p-3 text-xs">{faNum(s.tokens_discounted_7d)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
