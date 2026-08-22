'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice, faPercent } from '@/lib/format'
import { SectionHeader, Field } from './shared'

/* ═══════════════════════════════════════════════════════════════════════════
   Markup — profit percentage, global + per-model override (owner request,
   2026-08-22; see docs/NEXT-SESSION.md section 12).

   Self-contained (fetches its own data via the `api` helper AdminPanel
   already exposes, same pattern as ./components/MonitoringTab.tsx) rather
   than threading more state through AdminPanel.tsx, which is already over
   its own 500-line cap.

   Server contract (backend/admin_catalog.py):
     GET  /api/admin/markup/global          -> { markup_pct }
     POST /api/admin/markup/global          <- { markup_pct }
     GET  /api/admin/markup/models          -> [{ id, display_name,
                                                    input_per_million,
                                                    output_per_million,
                                                    markup_pct }]
     POST /api/admin/markup/models/{id}     <- { markup_pct: number | null }
     POST /api/admin/markup/models/bulk     <- { ids: string[], markup_pct: number | null }

   `markup_pct: null` on a model means "inherit the global" -- that is also
   what clearing an override sends. The price preview shown here
   (previewPrice) mirrors backend/content.py's apply_markup() rounding rule
   so what the operator sees before saving matches what the catalog/billing
   endpoints will actually serve after saving -- but the server value is
   always authoritative; this component reloads from it after every write
   rather than trusting its own arithmetic.
   ═══════════════════════════════════════════════════════════════════════════ */

interface ModelMarkupRow {
  id: string
  display_name: string
  input_per_million: number | null
  output_per_million: number | null
  markup_pct: number | null
}

interface MarkupSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

/** Client-side preview only -- mirrors content.apply_markup()'s
    round-to-nearest-toman rule. The server recomputes and is authoritative. */
function previewPrice(base: number | null | undefined, pct: number): number {
  return Math.round((base || 0) * (1 + pct / 100))
}

export default function MarkupSection({ api }: MarkupSectionProps) {
  const [loading, setLoading] = useState(true)

  const [globalPct, setGlobalPct] = useState(0)
  const [globalInput, setGlobalInput] = useState('0')
  const [savingGlobal, setSavingGlobal] = useState(false)

  const [rows, setRows] = useState<ModelMarkupRow[]>([])
  const [rowInputs, setRowInputs] = useState<Record<string, string>>({})
  const [savingRow, setSavingRow] = useState<string | null>(null)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkInput, setBulkInput] = useState('0')
  const [bulkSaving, setBulkSaving] = useState(false)
  const [filter, setFilter] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [gRes, mRes] = await Promise.all([
        api('/api/admin/markup/global'),
        api('/api/admin/markup/models'),
      ])
      const g = await gRes.json()
      const m: ModelMarkupRow[] = await mRes.json()
      const g_pct = Number(g.markup_pct) || 0
      setGlobalPct(g_pct)
      setGlobalInput(String(g_pct))
      setRows(m)
      // Reset per-row draft inputs to the server's current values so a
      // reload never leaves a stale edit sitting in an input box.
      const next: Record<string, string> = {}
      for (const r of m) next[r.id] = r.markup_pct == null ? '' : String(r.markup_pct)
      setRowInputs(next)
    } catch {
      toast('خطا در دریافت اطلاعات درصد سود', 'error')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  const saveGlobal = async () => {
    const pct = Number(globalInput)
    if (!Number.isFinite(pct) || pct < 0) {
      toast('درصد سود نمی‌تواند منفی باشد', 'error')
      return
    }
    setSavingGlobal(true)
    try {
      await api('/api/admin/markup/global', { method: 'POST', body: JSON.stringify({ markup_pct: pct }) })
      toast('درصد سراسری ذخیره شد', 'success')
      await load()
    } catch {
      toast('ذخیره درصد سراسری ناموفق بود', 'error')
    } finally {
      setSavingGlobal(false)
    }
  }

  const saveRowOverride = async (id: string) => {
    const raw = (rowInputs[id] ?? '').trim()
    const pct = raw === '' ? null : Number(raw)
    if (pct !== null && (!Number.isFinite(pct) || pct < 0)) {
      toast('درصد سود نمی‌تواند منفی باشد', 'error')
      return
    }
    setSavingRow(id)
    try {
      await api(`/api/admin/markup/models/${encodeURIComponent(id)}`, {
        method: 'POST', body: JSON.stringify({ markup_pct: pct }),
      })
      toast(pct === null ? 'override پاک شد — این مدل درصد سراسری را دارد' : 'override این مدل ذخیره شد', 'success')
      await load()
    } catch {
      toast('ذخیره ناموفق بود', 'error')
    } finally {
      setSavingRow(null)
    }
  }

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAllVisible = (ids: string[]) => {
    setSelected((prev) => {
      const allSelected = ids.every((id) => prev.has(id))
      const next = new Set(prev)
      if (allSelected) ids.forEach((id) => next.delete(id))
      else ids.forEach((id) => next.add(id))
      return next
    })
  }

  const bulkApply = async (clear: boolean) => {
    if (selected.size === 0) {
      toast('حداقل یک مدل را انتخاب کنید', 'error')
      return
    }
    let pct: number | null = null
    if (!clear) {
      pct = Number(bulkInput)
      if (!Number.isFinite(pct) || pct < 0) {
        toast('درصد سود نمی‌تواند منفی باشد', 'error')
        return
      }
    }
    setBulkSaving(true)
    try {
      const r = await api('/api/admin/markup/models/bulk', {
        method: 'POST',
        body: JSON.stringify({ ids: Array.from(selected), markup_pct: pct }),
      })
      const body = await r.json()
      toast(`${faNum(body.updated ?? selected.size)} مدل به‌روزرسانی شد`, 'success')
      setSelected(new Set())
      await load()
    } catch {
      toast('اعمال گروهی ناموفق بود', 'error')
    } finally {
      setBulkSaving(false)
    }
  }

  const visibleRows = useMemo(() => {
    const q = filter.trim()
    if (!q) return rows
    return rows.filter((r) => r.id.includes(q) || (r.display_name || '').includes(q))
  }, [rows, filter])

  const visibleIds = useMemo(() => visibleRows.map((r) => r.id), [visibleRows])
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id))

  return (
    <div className="space-y-6">
      <SectionHeader
        title="درصد سود"
        subtitle="یک درصد سراسری روی همهٔ مدل‌ها، به‌علاوهٔ امکان override روی هر مدل — مدل بدون override از درصد سراسری ارث می‌برد"
      />

      {/* Global percentage */}
      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-1 text-primary">درصد سراسری</h3>
        <p className="text-xs text-muted mb-4">
          روی همهٔ مدل‌هایی که override اختصاصی ندارند اعمال می‌شود. مقدار فعلی: {faPercent(globalPct)}
        </p>
        <div className="flex items-end gap-4 flex-wrap">
          <Field label="درصد سود سراسری">
            <input
              className="input w-full"
              type="number"
              min={0}
              step="0.1"
              value={globalInput}
              onChange={(e) => setGlobalInput(e.target.value)}
              style={{ maxWidth: 160 }}
            />
          </Field>
          <button className="btn" onClick={saveGlobal} disabled={savingGlobal}>
            {savingGlobal ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>ذخیره درصد سراسری</span></>)}
          </button>
          <span className="text-xs text-muted">
            نمونه: قیمت پایه {faPrice(1_000_000)} با این درصد می‌شود {faPrice(previewPrice(1_000_000, Number(globalInput) || 0))}
          </span>
        </div>
      </div>

      {/* Bulk edit */}
      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-1 text-primary">ویرایش گروهی</h3>
        <p className="text-xs text-muted mb-4">
          {selected.size > 0 ? `${faNum(selected.size)} مدل انتخاب شده` : 'از جدول زیر مدل‌ها را انتخاب کنید'}
        </p>
        <div className="flex items-end gap-4 flex-wrap">
          <Field label="درصد سود برای مدل‌های انتخاب‌شده">
            <input
              className="input w-full"
              type="number"
              min={0}
              step="0.1"
              value={bulkInput}
              onChange={(e) => setBulkInput(e.target.value)}
              style={{ maxWidth: 160 }}
            />
          </Field>
          <button className="btn" onClick={() => bulkApply(false)} disabled={bulkSaving || selected.size === 0}>
            {bulkSaving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>اعمال روی انتخاب‌شده‌ها</span></>)}
          </button>
          <button
            className="btn btn-sm"
            style={{ background: 'var(--bg-elevated)' }}
            onClick={() => bulkApply(true)}
            disabled={bulkSaving || selected.size === 0}
            title="override این مدل‌ها را پاک می‌کند تا دوباره از درصد سراسری ارث ببرند"
          >
            <Icon name="trash" size={14} />
            <span>پاک کردن override</span>
          </button>
        </div>
      </div>

      {/* Per-model table */}
      <div className="admin-card">
        <div className="flex items-center justify-between gap-4 mb-4 flex-wrap">
          <h3 className="font-semibold text-sm text-primary">درصد به ازای هر مدل</h3>
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
                <th className="text-right p-3">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={() => toggleSelectAllVisible(visibleIds)}
                    aria-label="انتخاب همه"
                  />
                </th>
                <th className="text-right p-3">مدل</th>
                <th className="text-right p-3">قیمت پایه ورودی</th>
                <th className="text-right p-3">قیمت پایه خروجی</th>
                <th className="text-right p-3">درصد مؤثر</th>
                <th className="text-right p-3">قیمت ورودی پس از سود</th>
                <th className="text-right p-3">override این مدل</th>
                <th className="text-right p-3">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">در حال بارگذاری…</td></tr>
              ) : visibleRows.length === 0 ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">مدلی یافت نشد</td></tr>
              ) : (
                visibleRows.map((r) => {
                  const effectivePct = r.markup_pct ?? globalPct
                  const draft = rowInputs[r.id] ?? ''
                  return (
                    <tr key={r.id}>
                      <td className="p-3">
                        <input
                          type="checkbox"
                          checked={selected.has(r.id)}
                          onChange={() => toggleSelected(r.id)}
                          aria-label={`انتخاب ${r.display_name}`}
                        />
                      </td>
                      <td className="p-3">
                        <div className="text-sm font-medium text-primary">{r.display_name}</div>
                        <div className="text-xs font-mono text-muted">{r.id}</div>
                      </td>
                      <td className="p-3 text-xs">{faNum(r.input_per_million)}</td>
                      <td className="p-3 text-xs">{faNum(r.output_per_million)}</td>
                      <td className="p-3">
                        <span className="badge" title={r.markup_pct == null ? 'ارث‌برده از درصد سراسری' : 'override اختصاصی این مدل'}>
                          {faPercent(effectivePct)}
                          {r.markup_pct == null && <span className="text-muted"> (سراسری)</span>}
                        </span>
                      </td>
                      <td className="p-3 text-xs">{faPrice(previewPrice(r.input_per_million, effectivePct))}</td>
                      <td className="p-3">
                        <input
                          className="input"
                          type="number"
                          min={0}
                          step="0.1"
                          placeholder="سراسری"
                          value={draft}
                          onChange={(e) => setRowInputs((prev) => ({ ...prev, [r.id]: e.target.value }))}
                          style={{ maxWidth: 110 }}
                        />
                      </td>
                      <td className="p-3">
                        <button
                          className="btn btn-sm"
                          onClick={() => saveRowOverride(r.id)}
                          disabled={savingRow === r.id}
                          title={draft.trim() === '' ? 'خالی = پاک کردن override' : 'ذخیره override'}
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
