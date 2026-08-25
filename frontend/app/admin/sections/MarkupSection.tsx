'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice } from '@/lib/format'
import { errMessage } from '../api'
import { SectionHeader, Field } from './shared'
import MarkupModelsTable from './MarkupModelsTable'

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

   2026-08-25 (measured live: GET /api/admin/markup/models = 165,178 bytes,
   21,668 DOM nodes -- the worst tab in the panel, ~1,196 catalog rows all
   mounted at once). The table itself was split out to ./MarkupModelsTable.tsx,
   which windows it: only one page of rows is ever in the DOM, while search
   still runs over the full fetched array (see that file's header comment
   for the paging/selection contract). This file keeps the data fetch/save
   plumbing and the global + bulk-edit cards, which are small and fixed-size
   regardless of catalog size.
   ═══════════════════════════════════════════════════════════════════════════ */

export interface ModelMarkupRow {
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
    round-to-nearest-toman rule. The server recomputes and is authoritative.
    A percent is not money: dividing pct by 100 here is ordinary arithmetic,
    not a violation of the toman-integer rule (which governs the `base`
    money value, never touched by /10 or *10). */
export function previewPrice(base: number | null | undefined, pct: number): number {
  return Math.round((base || 0) * (1 + pct / 100))
}

/** Verified against backend/admin_catalog.py's _parse_markup_pct in this
    same change wave: it now rejects pct < 0 (existing) AND pct > 1000 (new).
    Mirrored here so a fat-fingered "700" instead of "7" is stopped before
    the round trip, not just before the server's Persian refusal comes back.
    Keep this in sync with the server if the cap ever moves -- it is
    deliberately not imported from anywhere because there is nowhere shared
    to import it from across the fetch boundary. */
export const MARKUP_PCT_MAX = 1000

/** Matches the server's exact wording (backend/admin_catalog.py) so the
    negative-percent refusal reads the same whether it was caught here or
    echoed back from the API. */
export function validateMarkupPct(pct: number): string | null {
  if (!Number.isFinite(pct) || pct < 0) return 'درصد سود نمی‌تواند منفی باشد (هیچ درخواستی نباید ضررده باشد)'
  if (pct > MARKUP_PCT_MAX) return `درصد سود نمی‌تواند بیش از ${faNum(MARKUP_PCT_MAX)}٪ باشد`
  return null
}

/** A bare <input type=number> never says whether "7" means 7% or 0.07 --
    the unit lived only in a preview line an admin can miss. The "٪" sits
    next to every percent input now, not just in the price-preview text. */
export function PercentInput({ value, onChange, placeholder, maxWidth = 110, disabled }: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  maxWidth?: number
  disabled?: boolean
}) {
  return (
    <div className="flex items-center gap-1.5" style={{ maxWidth }}>
      <input
        className="input"
        type="number"
        min={0}
        max={MARKUP_PCT_MAX}
        step="0.1"
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
      <span className="text-sm text-muted" aria-hidden="true">٪</span>
    </div>
  )
}

export default function MarkupSection({ api }: MarkupSectionProps) {
  const [loading, setLoading] = useState(true)
  // Distinct from an empty table: a failed load must not look like "zero
  // models exist" once the toast fades (see PlansSection's plansError).
  const [loadError, setLoadError] = useState<string | null>(null)

  const [globalPct, setGlobalPct] = useState(0)
  const [globalInput, setGlobalInput] = useState('0')
  const [savingGlobal, setSavingGlobal] = useState(false)

  const [rows, setRows] = useState<ModelMarkupRow[]>([])
  const [rowInputs, setRowInputs] = useState<Record<string, string>>({})
  const [savingRow, setSavingRow] = useState<string | null>(null)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkInput, setBulkInput] = useState('0')
  const [bulkSaving, setBulkSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
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
    } catch (err) {
      const msg = errMessage(err, 'خطا در دریافت اطلاعات درصد سود')
      setLoadError(msg)
      toast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  const saveGlobal = async () => {
    const pct = Number(globalInput)
    const err = validateMarkupPct(pct)
    if (err) { toast(err, 'error'); return }
    setSavingGlobal(true)
    try {
      await api('/api/admin/markup/global', { method: 'POST', body: JSON.stringify({ markup_pct: pct }) })
      toast('درصد سراسری ذخیره شد', 'success')
      await load()
    } catch (err) {
      toast(errMessage(err, 'ذخیره درصد سراسری ناموفق بود'), 'error')
    } finally {
      setSavingGlobal(false)
    }
  }

  const saveRowOverride = async (id: string) => {
    const raw = (rowInputs[id] ?? '').trim()
    const pct = raw === '' ? null : Number(raw)
    if (pct !== null) {
      const err = validateMarkupPct(pct)
      if (err) { toast(err, 'error'); return }
    }
    setSavingRow(id)
    try {
      await api(`/api/admin/markup/models/${encodeURIComponent(id)}`, {
        method: 'POST', body: JSON.stringify({ markup_pct: pct }),
      })
      toast(pct === null ? 'override پاک شد — این مدل درصد سراسری را دارد' : 'override این مدل ذخیره شد', 'success')
      await load()
    } catch (err) {
      toast(errMessage(err, 'ذخیره ناموفق بود'), 'error')
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

  /** Used both by "select this page" and by the explicit "select every
      row matching the search, across all pages" action in the table --
      the caller decides which id list to pass. */
  const setManySelected = (ids: string[], select: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (select) ids.forEach((id) => next.add(id))
      else ids.forEach((id) => next.delete(id))
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
      const err = validateMarkupPct(pct)
      if (err) { toast(err, 'error'); return }
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
    } catch (err) {
      toast(errMessage(err, 'اعمال گروهی ناموفق بود'), 'error')
    } finally {
      setBulkSaving(false)
    }
  }

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
          روی همهٔ مدل‌هایی که override اختصاصی ندارند اعمال می‌شود.
        </p>
        <div className="flex items-end gap-4 flex-wrap">
          <Field label="درصد سود سراسری">
            <PercentInput value={globalInput} onChange={setGlobalInput} maxWidth={140} />
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
            <PercentInput value={bulkInput} onChange={setBulkInput} maxWidth={140} />
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

      {/* Per-model table -- windowed, see MarkupModelsTable.tsx header comment */}
      <MarkupModelsTable
        rows={rows}
        rowInputs={rowInputs}
        onRowInputChange={(id, v) => setRowInputs((prev) => ({ ...prev, [id]: v }))}
        savingRow={savingRow}
        onSaveRow={saveRowOverride}
        selected={selected}
        onToggleSelected={toggleSelected}
        onSetManySelected={setManySelected}
        globalPct={globalPct}
        loading={loading}
        loadError={loadError}
        onRetry={load}
      />
    </div>
  )
}
