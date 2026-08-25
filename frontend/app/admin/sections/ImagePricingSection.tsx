'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice, faPercent } from '@/lib/format'
import { SectionHeader, Field } from './shared'
import { availabilityLabel } from './availability'

/* ═══════════════════════════════════════════════════════════════════════════
   Image pricing — per-model base Toman price for POST /v1/images/generations
   (backend/images.py). Migration 0032 added model_catalog.image_price_per_unit,
   NULL on every row; images.py hard-refuses any request for a model whose
   price is NULL (the product rule: no request may ever be loss-making), so
   until an admin sets a price here, image generation cannot serve anything.

   Self-contained (fetches its own data via the `api` helper AdminPanel
   already exposes), same pattern as ./MarkupSection.tsx.

   Server contract (backend/admin_catalog.py):
     GET  /api/admin/catalog/media-models          -> [{ id, provider_model_id,
                                                          display_name, availability,
                                                          image_price_per_unit,
                                                          markup_pct }]
     POST /api/admin/catalog/models/{id}/image-price <- { image_price_per_unit: number | null }

   `image_price_per_unit` is a BASE Toman price for one generated image,
   before markup_pct is applied — the same composition rule token pricing
   already follows (see MarkupSection.tsx). It must be a plain integer
   Toman amount or null (to unset); the server rejects floats outright,
   since the DB column is `numeric` with no scale constraint and integer
   Toman is the project-wide money rule. Every price shown here goes
   through faPrice fed the raw Toman value — never multiplied or divided
   by 10 anywhere in this file.
   ═══════════════════════════════════════════════════════════════════════════ */

interface MediaModelRow {
  id: string
  provider_model_id: string
  display_name: string
  availability: string
  image_price_per_unit: number | null
  markup_pct: number | null
}

interface ImagePricingSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

/** Client-side preview only — mirrors content.apply_markup()'s
    round-to-nearest-toman rule. The server recomputes and is authoritative. */
function previewPrice(base: number | null | undefined, pct: number | null): number {
  return Math.round((base || 0) * (1 + (pct || 0) / 100))
}

export default function ImagePricingSection({ api }: ImagePricingSectionProps) {
  const [loading, setLoading] = useState(true)
  const [rows, setRows] = useState<MediaModelRow[]>([])
  const [rowInputs, setRowInputs] = useState<Record<string, string>>({})
  const [savingRow, setSavingRow] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  // Distinct from an empty table: a failed load must not look like "no
  // image models exist" once the toast fades.
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const res = await api('/api/admin/catalog/media-models')
      const m: MediaModelRow[] = await res.json()
      setRows(m)
      // Reset per-row draft inputs to the server's current values so a
      // reload never leaves a stale edit sitting in an input box.
      const next: Record<string, string> = {}
      for (const r of m) next[r.id] = r.image_price_per_unit == null ? '' : String(r.image_price_per_unit)
      setRowInputs(next)
    } catch (err) {
      const msg = err instanceof Error && err.message !== 'unauthorized' ? err.message : 'خطا در دریافت مدل‌های تصویری'
      setLoadError(msg)
      toast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  const saveRowPrice = async (id: string) => {
    const raw = (rowInputs[id] ?? '').trim()
    let price: number | null = null
    if (raw !== '') {
      if (!/^-?\d+$/.test(raw)) {
        toast('قیمت باید عدد صحیح تومان باشد (اعشار مجاز نیست)', 'error')
        return
      }
      price = Number(raw)
      if (price < 0) {
        toast('قیمت نمی‌تواند منفی باشد', 'error')
        return
      }
    }
    setSavingRow(id)
    try {
      // `api()` (AdminPanel.tsx) throws on any non-2xx response, so a
      // non-ok result is handled in the catch below, not here -- matching
      // MarkupSection.tsx's saveRowOverride, which follows the same rule.
      await api(`/api/admin/catalog/models/${encodeURIComponent(id)}/image-price`, {
        method: 'POST', body: JSON.stringify({ image_price_per_unit: price }),
      })
      toast(price === null ? 'قیمت پاک شد — این مدل دیگر قابل ارائه نیست' : 'قیمت این مدل ذخیره شد', 'success')
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'ذخیره ناموفق بود', 'error')
    } finally {
      setSavingRow(null)
    }
  }

  const visibleRows = useMemo(() => {
    const q = filter.trim()
    if (!q) return rows
    return rows.filter((r) => r.id.includes(q) || (r.display_name || '').includes(q))
  }, [rows, filter])

  const unpricedCount = useMemo(() => rows.filter((r) => r.image_price_per_unit == null).length, [rows])

  return (
    <div className="space-y-6">
      <SectionHeader
        title="قیمت‌گذاری تصویر"
        subtitle="قیمت پایه (تومان) برای هر تصویر تولیدشده — مدل بدون قیمت هرگز به کاربر ارائه نمی‌شود"
      />

      {unpricedCount > 0 && !loading && (
        <div className="admin-card flex items-center gap-3" style={{ borderRight: '3px solid var(--warning)' }}>
          <Icon name="notification" size={18} style={{ color: 'var(--warning)' }} />
          <span className="text-sm" style={{ color: 'var(--warning)' }}>
            {faNum(unpricedCount)} مدل تصویری بدون قیمت — تا قیمت‌گذاری نشوند قابل ارائه نیستند
          </span>
        </div>
      )}

      <div className="admin-card">
        <div className="flex items-center justify-between gap-4 mb-4 flex-wrap">
          <h3 className="font-semibold text-sm text-primary">مدل‌های تصویری</h3>
          <input
            className="input"
            placeholder="جستجوی مدل…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ maxWidth: 220 }}
          />
        </div>
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-3">مدل</th>
                <th className="text-right p-3">وضعیت</th>
                <th className="text-right p-3">قیمت پایه (تومان)</th>
                {/* Read-only here. The column is `model_catalog.markup_pct`, written
                    only from the «درصد سود» sub-tab -- an admin looking at a wrong
                    final price on this screen has no way to know which control
                    produced it unless the screen says so. Same reason PricingSection
                    points at «عملیات کاتالوگ» for the availability it cannot change. */}
                <th className="text-right p-3">
                  درصد سود
                  <span className="block text-[10px] font-normal text-muted">از تب «درصد سود»</span>
                </th>
                <th className="text-right p-3">قیمت نهایی هر تصویر</th>
                <th className="text-right p-3">قیمت جدید</th>
                <th className="text-right p-3">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="p-6 text-center text-sm text-muted">در حال بارگذاری…</td></tr>
              ) : loadError ? (
                <tr><td colSpan={7} className="p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
                  {loadError} — <button className="underline" onClick={load}>تلاش دوباره</button>
                </td></tr>
              ) : visibleRows.length === 0 ? (
                <tr><td colSpan={7} className="p-6 text-center text-sm text-muted">مدل تصویری یافت نشد</td></tr>
              ) : (
                visibleRows.map((r) => {
                  const draft = rowInputs[r.id] ?? ''
                  const finalPrice = r.image_price_per_unit == null
                    ? null
                    : previewPrice(r.image_price_per_unit, r.markup_pct)
                  return (
                    <tr key={r.id}>
                      <td className="p-3">
                        <div className="text-sm font-medium text-primary">{r.display_name}</div>
                        <div className="text-xs font-mono text-muted">{r.id}</div>
                      </td>
                      <td className="p-3">
                        <span className="badge">{availabilityLabel(r.availability)}</span>
                      </td>
                      <td className="p-3 text-xs">
                        {r.image_price_per_unit == null ? (
                          <span className="text-muted">تعیین نشده</span>
                        ) : (
                          faPrice(r.image_price_per_unit)
                        )}
                      </td>
                      <td className="p-3 text-xs">
                        {r.markup_pct == null ? (
                          <span className="text-muted">سراسری</span>
                        ) : (
                          faPercent(r.markup_pct)
                        )}
                      </td>
                      <td className="p-3 text-xs">
                        {finalPrice == null ? <span className="text-muted">—</span> : faPrice(finalPrice)}
                      </td>
                      <td className="p-3">
                        <input
                          className="input"
                          type="number"
                          min={0}
                          step={1}
                          placeholder="بدون قیمت"
                          value={draft}
                          onChange={(e) => setRowInputs((prev) => ({ ...prev, [r.id]: e.target.value }))}
                          style={{ maxWidth: 130 }}
                        />
                      </td>
                      <td className="p-3">
                        <button
                          className="btn btn-sm"
                          onClick={() => saveRowPrice(r.id)}
                          disabled={savingRow === r.id}
                          title={draft.trim() === '' ? 'خالی = پاک کردن قیمت (مدل قابل ارائه نمی‌شود)' : 'ذخیره قیمت'}
                        >
                          {savingRow === r.id ? (
                            <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                          ) : <Icon name="check" size={14} />}
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
