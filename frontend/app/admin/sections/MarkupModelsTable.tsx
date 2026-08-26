'use client'

import { useState, useMemo, useEffect } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { previewPrice, PercentInput, type ModelMarkupRow } from './MarkupSection'
import { markupModelsTableStrings } from './MarkupModelsTable.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   The per-model markup table -- split out of MarkupSection.tsx 2026-08-25
   because it was the single worst DOM offender in the whole admin panel:
   measured live, GET /api/admin/markup/models returns the full ~1,196-row
   catalog and the old table mounted every row (checkbox + number input +
   button each) at once = 21,668 DOM nodes inside <main>, against a median
   of under 400 nodes for every other sub-tab.

   Fix is plain array slicing (PAGE_SIZE per page) -- no virtualisation
   library, matching how paged tables elsewhere in the panel already work
   (ModerationSection's EVENTS_PAGE_SIZE, LogicalModelsSection's `limit`).
   Those are server-side paged; this endpoint isn't (it returns the whole
   catalog in one call and that contract is unchanged in this wave), so the
   slicing happens client-side on the array already in memory.

   Two rules that keep this correct rather than just fast:

   1. SEARCH RUNS ON THE FULL DATASET, NOT THE CURRENT PAGE. `filtered` is
      computed from the `rows` prop (the whole fetched catalog), then paged
      -- never the other way around. A search box that can only find
      whatever happened to be on the currently-rendered page would silently
      hide matches, which is worse than no search at all.

   2. SELECTION SURVIVES PAGING, AND CROSS-PAGE SELECT-ALL IS AN EXPLICIT,
      NAMED ACTION -- NOT AN ACCIDENT OF THE HEADER CHECKBOX. The bulk-apply
      Set lives in the parent (MarkupSection) and is never cleared on page
      or filter change, so paging away and back keeps a selection intact.
      But the header checkbox in this table only ever selects/deselects the
      rows on the CURRENT page -- ticking it must never silently reach into
      pages the admin cannot currently see. Selecting every row that matches
      the search, across every page, is only ever done via the separate
      "انتخاب همهٔ N نتیجه (همهٔ صفحات)" button below the search box, whose
      label states exactly how many rows and that it spans every page. That
      button is the one deliberate way to apply a markup to more than what's
      on screen; silently doing it from a checkbox would be exactly the kind
      of "applied to a different set than the admin believed they selected"
      money bug this rework exists to prevent.
   ═══════════════════════════════════════════════════════════════════════════ */

const PAGE_SIZE = 50

interface MarkupModelsTableProps {
  rows: ModelMarkupRow[]
  rowInputs: Record<string, string>
  onRowInputChange: (id: string, value: string) => void
  savingRow: string | null
  onSaveRow: (id: string) => void
  selected: Set<string>
  onToggleSelected: (id: string) => void
  onSetManySelected: (ids: string[], select: boolean) => void
  globalPct: number
  loading: boolean
  loadError: string | null
  onRetry: () => void
}

export default function MarkupModelsTable({
  rows, rowInputs, onRowInputChange, savingRow, onSaveRow,
  selected, onToggleSelected, onSetManySelected,
  globalPct, loading, loadError, onRetry,
}: MarkupModelsTableProps) {
  const lang = useLang()
  const s = markupModelsTableStrings(lang)
  const f = fmt(lang)
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(1)

  const filteredRows = useMemo(() => {
    const q = filter.trim()
    if (!q) return rows
    return rows.filter((r) => r.id.includes(q) || (r.display_name || '').includes(q))
  }, [rows, filter])

  const pageCount = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE))

  // A new search or a shrunk result set (or a page the admin was on that no
  // longer exists after a reload) must not strand them on a blank page.
  useEffect(() => { setPage(1) }, [filter])
  useEffect(() => { setPage((p) => Math.min(p, pageCount)) }, [pageCount])

  const pagedRows = useMemo(
    () => filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredRows, page],
  )

  const pagedIds = useMemo(() => pagedRows.map((r) => r.id), [pagedRows])
  const allPageSelected = pagedIds.length > 0 && pagedIds.every((id) => selected.has(id))
  const allFilteredSelected = filteredRows.length > 0 && filteredRows.every((r) => selected.has(r.id))

  return (
    <div className="admin-card">
      <div className="flex items-center justify-between gap-4 mb-2 flex-wrap">
        <h3 className="font-semibold text-sm text-primary">{s.title}</h3>
        <input
          className="input"
          placeholder={s.searchPlaceholder}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ maxWidth: 220 }}
        />
      </div>
      <div className="flex items-center justify-between gap-4 mb-4 flex-wrap text-xs text-muted">
        <span>{s.summary(f.num(filteredRows.length), f.num(page), f.num(pageCount))}</span>
        <button
          className="underline"
          onClick={() => onSetManySelected(filteredRows.map((r) => r.id), !allFilteredSelected)}
          disabled={filteredRows.length === 0}
        >
          {allFilteredSelected ? s.deselectAllFiltered : s.selectAllFiltered(f.num(filteredRows.length))}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="admin-table w-full text-sm">
          <thead>
            <tr>
              <th className="text-right p-3">
                <input
                  type="checkbox"
                  checked={allPageSelected}
                  onChange={() => onSetManySelected(pagedIds, !allPageSelected)}
                  aria-label={s.selectPageAria}
                  title={s.selectPageTitle}
                />
              </th>
              <th className="text-right p-3">{s.colModel}</th>
              <th className="text-right p-3">{s.colBaseInput}</th>
              <th className="text-right p-3">{s.colBaseOutput}</th>
              <th className="text-right p-3">{s.colEffectivePct}</th>
              <th className="text-right p-3">{s.colInputAfterMarkup}</th>
              <th className="text-right p-3">{s.colOverride}</th>
              <th className="text-right p-3">{s.colActions}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">{s.loading}</td></tr>
            ) : loadError ? (
              <tr><td colSpan={8} className="p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
                {loadError} — <button className="underline" onClick={onRetry}>{s.retry}</button>
              </td></tr>
            ) : pagedRows.length === 0 ? (
              <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">{s.noModels}</td></tr>
            ) : (
              pagedRows.map((r) => {
                const effectivePct = r.markup_pct ?? globalPct
                const draft = rowInputs[r.id] ?? ''
                return (
                  <tr key={r.id}>
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={selected.has(r.id)}
                        onChange={() => onToggleSelected(r.id)}
                        aria-label={s.selectRowAria(r.display_name)}
                      />
                    </td>
                    <td className="p-3">
                      <div className="text-sm font-medium text-primary">{r.display_name}</div>
                      <div className="text-xs font-mono text-muted" dir="ltr">{r.id}</div>
                    </td>
                    <td className="p-3 text-xs">{f.num(r.input_per_million)}</td>
                    <td className="p-3 text-xs">{f.num(r.output_per_million)}</td>
                    <td className="p-3">
                      <span className="badge" title={r.markup_pct == null ? s.inheritedTitle : s.overrideTitle}>
                        {f.percent(effectivePct)}
                        {r.markup_pct == null && <span className="text-muted">{s.globalSuffix}</span>}
                      </span>
                    </td>
                    <td className="p-3 text-xs">{f.price(previewPrice(r.input_per_million, effectivePct))}</td>
                    <td className="p-3">
                      <PercentInput
                        value={draft}
                        onChange={(v) => onRowInputChange(r.id, v)}
                        placeholder={s.overridePlaceholder}
                      />
                    </td>
                    <td className="p-3">
                      <button
                        className="btn btn-sm"
                        onClick={() => onSaveRow(r.id)}
                        disabled={savingRow === r.id}
                        title={draft.trim() === '' ? s.saveEmptyTitle : s.saveTitle}
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
      {!loading && !loadError && pageCount > 1 && (
        <div className="flex items-center justify-between gap-4 mt-4 flex-wrap">
          <span className="text-xs text-muted">{s.page(f.num(page), f.num(pageCount))}</span>
          <div className="flex gap-2">
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>{s.prev}</button>
            <button className="btn btn-sm" disabled={page >= pageCount} onClick={() => setPage((p) => Math.min(pageCount, p + 1))}>{s.next}</button>
          </div>
        </div>
      )}
    </div>
  )
}
