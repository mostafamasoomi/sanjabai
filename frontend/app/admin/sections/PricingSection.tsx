'use client'

import { useState, useMemo, useEffect } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { api, errMessage } from '../api'
import { useAdminResource } from '../useAdminResource'
import type { PricingRow, ModelTestResult } from '../types'
import { availabilityLabel, AVAILABILITY_BADGE, TOGGLEABLE } from './availability'
import { pricingStrings } from './PricingSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Pricing — per-model tariffs: GET/POST /admin/pricing, plus the per-model
   availability toggle and live probe (backend/admin_pricing.py).

   The credit/token package table and form that used to sit at the bottom of
   this screen are GONE. They wrote to POST /admin/credit-packages in
   backend/admin_plans.py, which hardcoded `active: true` and skipped the
   loss-path validation that POST /admin/packages runs — two admin screens
   writing the same table, one of them able to publish a package that sells
   at a loss. PackagesSection is now the only writer, and admin_plans.py
   itself was deleted with the plan/subscription concept (migration 0049),
   so that unvalidated endpoint no longer exists at all.

   Price editing is now INLINE, per row, instead of a name-typed form at the
   bottom of the page. The old form let an admin type any string into a
   "model name" text field and gated Save on a client-side `knownModel`
   lookup, because POST /admin/pricing only UPDATEs an existing
   model_catalog row (admin_pricing.py's set_pricing 404s on rowcount 0) —
   it never INSERTs. Editing the row itself removes that whole class of bug
   by construction: there is no name field, so there is nothing to typo.

   Rows are windowed (plain array slicing, PAGE_SIZE below) instead of all
   ~1,200 being mounted at once. The unwindowed table measured 18,064 DOM
   nodes in <main> against 150-1,456 for every other tab in this module and
   added ~900ms of pure render/layout time on top of a 67ms-fast fetch.
   Filtering still runs over the full fetched dataset -- only the *rendered*
   window is capped, so a search never misses a match that happens to be on
   another page.
   ═══════════════════════════════════════════════════════════════════════════ */

// Labels and badge classes come from ./availability.ts. They used to be a
// local literal carrying a comment that claimed it was hand-synced with the
// other tabs' copies; it was not -- this file rendered «فعال»/«تعمیرات»
// where the catalog tab rendered «در دسترس»/«در تعمیر» for the same row.
// POST /admin/models/{id}/toggle (admin_pricing.py) only flips between
// these two -- it 400s on anything else. Rendering it as a clickable toggle
// on a 'maintenance'/'degraded' row used to look identical to a real
// available/disabled row and, on a free upstream, would silently put an
// unprobed model up for sale on one misclick.

// Same page size ModelOpsSection.tsx already uses for the same ~1,200-row
// model_catalog table -- keeping it identical means the two tabs behave the
// same way for the same dataset instead of one paginating tighter than the
// other for no reason.
const PAGE_SIZE = 50

/** Never show a raw currency code -- every other screen that renders this
 *  same model_catalog.currency column (onboardingHelpers.ts, pricing/page.tsx)
 *  translates IRT/IRR to a display currency before rendering; this was the
 *  one place that didn't. */
function currencyLabel(code: string, s: ReturnType<typeof pricingStrings>): string {
  return code === 'IRT' ? s.currencyIrt : code === 'IRR' ? s.currencyIrr : code
}

type PriceFieldResult = { ok: true; value: number } | { ok: false; message: string }

// The bug this closes: `+pzIn || 0` turned an empty box, "abc", or any other
// non-numeric junk into a silent 0 that got POSTed straight to the server --
// no error, no confirmation, a model just started billing at zero toman.
// `0` itself stays a legal, deliberate value; only empty/garbage/negative/
// fractional input is rejected. Prices are integer toman per million tokens
// -- there is no smaller unit to express a fraction of a toman in.
function validatePriceField(raw: string, label: string, s: ReturnType<typeof pricingStrings>): PriceFieldResult {
  const trimmed = raw.trim()
  if (trimmed === '') return { ok: false, message: s.priceEmpty(label) }
  const n = Number(trimmed)
  if (!Number.isFinite(n)) return { ok: false, message: s.priceNotNumber(label) }
  if (n < 0) return { ok: false, message: s.priceNegative(label) }
  if (!Number.isInteger(n)) return { ok: false, message: s.priceNotInteger(label) }
  return { ok: true, value: n }
}

export default function PricingSection() {
  const lang = useLang()
  const s = pricingStrings(lang)
  const f = fmt(lang)

  const { data: prices, error, loading, reload, setData } = useAdminResource<PricingRow[]>(
    '/api/admin/pricing',
    (raw) => (Array.isArray(raw) ? raw : raw?.pricing || []),
    s.genericError,
  )

  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const [editingModel, setEditingModel] = useState<string | null>(null)
  const [editIn, setEditIn] = useState('')
  const [editOut, setEditOut] = useState('')
  const [editError, setEditError] = useState<string | null>(null)
  const [savingEdit, setSavingEdit] = useState(false)

  const [togglingModel, setTogglingModel] = useState<string | null>(null)
  const [testingModel, setTestingModel] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, ModelTestResult>>({})

  // Client-side only -- the catalog is ~1,200 rows in one GET (same as
  // ModelOpsSection's own read of this table). Runs over the full fetched
  // array, not the current page, so a match on page 9 is still found while
  // only the matching subset gets windowed for render below.
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return prices || []
    return (prices || []).filter((p) => {
      const displayName = String((p as { display_name?: string }).display_name || '')
      return p.model.toLowerCase().includes(q) || displayName.toLowerCase().includes(q)
    })
  }, [prices, search])

  useEffect(() => { setPage(1) }, [search])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const pageStart = filtered.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const pageEnd = Math.min(page * PAGE_SIZE, filtered.length)

  const startEdit = (p: PricingRow) => {
    setEditingModel(p.model)
    setEditIn(String(p.input_per_million))
    setEditOut(String(p.output_per_million))
    setEditError(null)
  }
  const cancelEdit = () => {
    setEditingModel(null)
    setEditIn('')
    setEditOut('')
    setEditError(null)
  }

  const saveEdit = async (model: string) => {
    const inRes = validatePriceField(editIn, s.fieldInput, s)
    if (!inRes.ok) { setEditError(inRes.message); return }
    const outRes = validatePriceField(editOut, s.fieldOutput, s)
    if (!outRes.ok) { setEditError(outRes.message); return }

    setEditError(null)
    setSavingEdit(true)
    try {
      await api('/api/admin/pricing', {
        method: 'POST',
        body: JSON.stringify({ model, input_per_million: inRes.value, output_per_million: outRes.value, currency: 'IRT' }),
      })
      toast(s.saveOk, 'success')
      setData((prev) => (prev || []).map((p) => (p.model === model ? { ...p, input_per_million: inRes.value, output_per_million: outRes.value } : p)))
      cancelEdit()
    } catch (err) {
      setEditError(errMessage(err, s.saveError))
    } finally {
      setSavingEdit(false)
    }
  }

  const toggleModel = async (model: string) => {
    setTogglingModel(model)
    try {
      const r = await api(`/api/admin/models/${encodeURIComponent(model)}/toggle`, { method: 'POST' })
      const data = await r.json()
      toast(data.availability === 'available' ? s.modelEnabled(model) : s.modelDisabled(model), 'success')
      setData((prev) => (prev || []).map((p) => (p.model === model ? { ...p, availability: data.availability } : p)))
    } catch (err) {
      toast(errMessage(err, s.toggleError), 'error')
    } finally {
      setTogglingModel(null)
    }
  }

  const testModel = async (model: string) => {
    setTestingModel(model)
    try {
      const r = await api(`/api/admin/models/${encodeURIComponent(model)}/test`, { method: 'POST' })
      const data: ModelTestResult = await r.json()
      setTestResults((prev) => ({ ...prev, [model]: data }))
      toast(
        data.ok ? s.testResponded(model, f.num(data.latency_ms)) : s.testFailed(model, data.error || s.testUnknownReason),
        data.ok ? 'success' : 'error',
      )
    } catch (err) {
      toast(errMessage(err, s.testModelError), 'error')
    } finally {
      setTestingModel(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title={s.title} subtitle={s.subtitle} />
        <RefreshButton onClick={reload} busy={loading} />
      </div>

      {error && <ErrorCard message={error} onRetry={reload} />}
      {!error && !prices && <CardSkeleton count={3} />}

      {prices && (
        <div className="admin-card overflow-x-auto">
          <div className="flex items-center gap-2 p-3">
            <input
              className="input w-full sm:w-72"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={s.searchPlaceholder}
            />
            <span className="text-xs text-muted">
              {s.matched(f.num(filtered.length), f.num(prices.length))}
            </span>
          </div>
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="p-3">{s.colModel}</th>
                <th className="p-3">{s.colInput}</th>
                <th className="p-3">{s.colOutput}</th>
                <th className="p-3">{s.colUnit}</th>
                <th className="p-3">{s.colStatus}</th>
                <th className="p-3">{s.colTest}</th>
                <th className="p-3">{s.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-sm text-muted">
                    {prices.length === 0 ? s.noPricing : s.noMatch}
                  </td>
                </tr>
              ) : (
                pageRows.map((p) => {
                  const isEditing = editingModel === p.model
                  const testResult = testResults[p.model]
                  const avail = p.availability || 'maintenance'
                  const badgeClass = `badge ${AVAILABILITY_BADGE[avail] || 'badge-accent'}`
                  const badgeLabel = availabilityLabel(avail, lang)
                  return (
                    <tr key={p.model}>
                      <td className="p-3 text-sm font-mono font-medium text-primary">{p.model}</td>
                      {isEditing ? (
                        <>
                          <td className="p-3">
                            <input
                              className="input w-28" type="number" value={editIn}
                              onChange={(e) => setEditIn(e.target.value)}
                              placeholder={s.inputPlaceholder} aria-label={s.inputAriaLabel(p.model)}
                            />
                          </td>
                          <td className="p-3">
                            <input
                              className="input w-28" type="number" value={editOut}
                              onChange={(e) => setEditOut(e.target.value)}
                              placeholder={s.inputPlaceholder} aria-label={s.outputAriaLabel(p.model)}
                            />
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="p-3 text-xs">{f.num(p.input_per_million)}</td>
                          <td className="p-3 text-xs">{f.num(p.output_per_million)}</td>
                        </>
                      )}
                      <td className="p-3"><span className="badge">{currencyLabel(p.currency, s)}</span></td>
                      <td className="p-3">
                        {TOGGLEABLE.has(avail) ? (
                          <button
                            className={badgeClass}
                            style={{ cursor: 'pointer' }}
                            disabled={togglingModel === p.model}
                            onClick={() => toggleModel(p.model)}
                            title={s.toggleTitle}
                          >
                            {togglingModel === p.model ? '...' : badgeLabel}
                          </button>
                        ) : (
                          <span className={badgeClass} title={s.toggleDisabledTitle}>
                            {badgeLabel}
                          </span>
                        )}
                      </td>
                      <td className="p-3">
                        <button className="btn btn-sm" disabled={testingModel === p.model} onClick={() => testModel(p.model)}>
                          {testingModel === p.model ? (
                            <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                          ) : s.test}
                        </button>
                        {testResult && (
                          <span className="text-xs mr-2" style={{ color: testResult.ok ? 'var(--success, #4ade80)' : 'var(--danger, #e35d5d)' }}>
                            {testResult.ok ? `${f.num(testResult.latency_ms)}ms` : (testResult.error || s.testError)}
                          </span>
                        )}
                      </td>
                      <td className="p-3">
                        {isEditing ? (
                          <div>
                            <div className="flex gap-1">
                              <button className="btn btn-sm" onClick={() => saveEdit(p.model)} disabled={savingEdit}>
                                {savingEdit ? (
                                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                                ) : <Icon name="check" size={14} />}
                              </button>
                              <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={cancelEdit} disabled={savingEdit}>
                                {s.cancel}
                              </button>
                            </div>
                            {editError && (
                              <p className="text-xs mt-1" style={{ color: 'var(--danger, #e35d5d)' }}>{editError}</p>
                            )}
                          </div>
                        ) : (
                          <button className="btn btn-sm" title={s.editTitle} onClick={() => startEdit(p)}>
                            <Icon name="settings" size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>

          {filtered.length > 0 && (
            <div className="flex items-center justify-between p-3 text-xs text-muted">
              <span>{s.pageRange(f.num(pageStart), f.num(pageEnd), f.num(filtered.length), f.num(page), f.num(totalPages))}</span>
              <div className="flex gap-2">
                <button className="btn btn-sm" onClick={() => setPage((n) => Math.max(1, n - 1))} disabled={page <= 1}>{s.prev}</button>
                <button className="btn btn-sm" onClick={() => setPage((n) => Math.min(totalPages, n + 1))} disabled={page >= totalPages}>{s.next}</button>
              </div>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-muted">
        {s.footerNote}
      </p>
    </div>
  )
}
