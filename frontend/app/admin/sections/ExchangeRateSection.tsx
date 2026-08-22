'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice, faDate, faTime } from '@/lib/format'
import { SectionHeader, StatCard } from './shared'

/* ═══════════════════════════════════════════════════════════════════════════
   نرخ ارز — نمایش نرخ زندهٔ دلار به تومان، منبع تأمین آن، و زمان آخرین
   به‌روزرسانی (درخواست مالک، ۲۲ مرداد ۱۴۰۵ / 2026-08-22).

   Self-contained (fetches via the `api` helper AdminPanel already exposes),
   same pattern as ./MarkupSection.tsx.

   Server contract (backend/exchange_rate_admin.py):
     GET  /api/admin/exchange-rate          -> {
       rate_irt_bare, flat_markup_irt, rate_irt_effective, markup_pct,
       source, fetched_at, cache_ttl_remaining_s
     }
     POST /api/admin/exchange-rate/refresh  -> same shape, forces a fresh resolve

   `source` mirrors backend/content.py's 4-tier resolver: 'db_override' >
   'tgju' > 'er_api' > 'hardcoded_fallback', plus 'unknown' for a cache entry
   written before this feature existed (a stale/unhealthy state, not a normal
   tier -- rendered distinctly on purpose, see SOURCE_META below). All money
   here is raw Toman straight from the server -- never multiplied or divided.
   ═══════════════════════════════════════════════════════════════════════════ */

interface ExchangeRateMeta {
  rate_irt_bare: number
  flat_markup_irt: number
  rate_irt_effective: number
  markup_pct: number
  source: string
  fetched_at: string | null
  cache_ttl_remaining_s: number | null
}

interface ExchangeRateSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

const SOURCE_META: Record<string, { label: string; color: string; healthy: boolean }> = {
  db_override: { label: 'override دستی در پایگاه داده', color: 'var(--accent, #6366f1)', healthy: true },
  tgju: { label: 'بازار زنده — tgju.org', color: 'var(--success, #22c55e)', healthy: true },
  er_api: { label: 'پشتیبان — open.er-api.com', color: 'var(--warning, #eab308)', healthy: true },
  hardcoded_fallback: { label: 'مقدار ثابت پشتیبان (کد)', color: 'var(--danger, #ef4444)', healthy: false },
  unknown: { label: 'نامشخص — کش قدیمی', color: 'var(--danger, #ef4444)', healthy: false },
}

function sourceMeta(source: string) {
  return SOURCE_META[source] || { label: source, color: 'var(--danger, #ef4444)', healthy: false }
}

export default function ExchangeRateSection({ api }: ExchangeRateSectionProps) {
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [meta, setMeta] = useState<ExchangeRateMeta | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api('/api/admin/exchange-rate')
      const body: ExchangeRateMeta = await res.json()
      setMeta(body)
    } catch {
      toast('خطا در دریافت نرخ ارز', 'error')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  const refresh = async () => {
    setRefreshing(true)
    try {
      const res = await api('/api/admin/exchange-rate/refresh', { method: 'POST' })
      const body: ExchangeRateMeta = await res.json()
      setMeta(body)
      toast('نرخ ارز به‌روزرسانی شد', 'success')
    } catch {
      toast('به‌روزرسانی نرخ ارز ناموفق بود', 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const sm = meta ? sourceMeta(meta.source) : null

  return (
    <div className="space-y-6">
      <SectionHeader
        title="نرخ ارز"
        subtitle="نرخ زندهٔ دلار به تومان که قیمت همهٔ مدل‌ها بر اساس آن محاسبه می‌شود — نرخ بازار، مارک‌آپ ثابت، منبع تأمین و زمان آخرین به‌روزرسانی"
      />

      {loading ? (
        <div className="admin-card p-6 text-center text-sm text-muted">در حال بارگذاری…</div>
      ) : !meta ? (
        <div className="admin-card p-6 text-center text-sm text-muted">اطلاعاتی یافت نشد</div>
      ) : (
        <>
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <StatCard icon="chart" label="نرخ بازار (بدون مارک‌آپ)" value={faPrice(Math.round(meta.rate_irt_bare))} color="var(--accent, #6366f1)" />
            <StatCard icon="plus" label="مارک‌آپ ثابت" value={faPrice(Math.round(meta.flat_markup_irt))} color="var(--warning, #eab308)" />
            <StatCard icon="wallet" label="نرخ مؤثر (سرو شده به کاربر)" value={faPrice(Math.round(meta.rate_irt_effective))} color="var(--success, #22c55e)" />
          </div>

          <div className="admin-card">
            <div className="flex items-center justify-between gap-4 flex-wrap mb-4">
              <h3 className="font-semibold text-sm text-primary">منبع و زمان به‌روزرسانی</h3>
              <button className="btn btn-sm" onClick={refresh} disabled={refreshing}>
                {refreshing ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (<><Icon name="refresh" size={14} /><span>واکشی فوری</span></>)}
              </button>
            </div>

            <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
              <div>
                <p className="text-xs text-muted mb-1">منبع نرخ</p>
                <span
                  className="badge"
                  title={sm && !sm.healthy ? 'وضعیت سالم نیست — این نرخ از یک کش قدیمی یا مقدار ثابت پشتیبان می‌آید، نه بازار زنده' : undefined}
                  style={{ color: sm?.color, borderColor: sm?.color }}
                >
                  {sm?.label}
                </span>
                {sm && !sm.healthy && (
                  <p className="text-xs mt-1" style={{ color: sm.color }}>
                    ⚠ این وضعیت سالم نیست — نرخ واقعی بازار تأمین نشده
                  </p>
                )}
              </div>
              <div>
                <p className="text-xs text-muted mb-1">آخرین واکشی</p>
                <p className="text-sm text-primary">
                  {meta.fetched_at ? `${faDate(meta.fetched_at)} — ${faTime(meta.fetched_at)}` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted mb-1">اعتبار کش</p>
                <p className="text-sm text-primary">
                  {meta.cache_ttl_remaining_s != null ? `${faNum(meta.cache_ttl_remaining_s)} ثانیهٔ دیگر` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted mb-1">درصد سود سراسری فعلی</p>
                <p className="text-sm text-primary">{faNum(meta.markup_pct)}٪</p>
              </div>
            </div>
          </div>

          <div className="admin-card">
            <p className="text-xs text-muted leading-6">
              نرخ سرو شده به کاربر همیشه برابر است با «نرخ بازار + مارک‌آپ ثابت»: {faPrice(Math.round(meta.rate_irt_bare))} + {faPrice(Math.round(meta.flat_markup_irt))} = {faPrice(Math.round(meta.rate_irt_effective))}.
              این عدد جدا از درصد سود هر مدل است که روی قیمت پایهٔ همان مدل اعمال می‌شود.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
