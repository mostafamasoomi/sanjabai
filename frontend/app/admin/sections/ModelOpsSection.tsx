'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader } from './shared'
import { errMessage } from '../api'
import { AVAILABILITY_OPTIONS, AVAILABILITY_COLOR, TOGGLEABLE, availabilityLabel, type Availability } from './availability'
import { BulkActionBar, BulkConfirmModal } from './ModelOpsBulkControls'
import CatalogFilterBar, { type ProbeFilter } from './CatalogFilterBar'
import { useBulkLiveTest, BulkLiveTestProgress, type TestResult } from './BulkLiveTest'
import BulkTestSummary from './BulkTestSummary'
import { modelOpsStrings } from './ModelOpsSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   ModelOps — catalog-wide availability operations. Distinct from the
   existing ./ModelsSection.tsx (now just the org default-model picker; the
   duplicate catalog table it used to embed has been deleted) and from
   ./MarkupSection.tsx (profit percentage only). This section is the only
   frontend consumer of the admin_catalog.py endpoints that operate on the
   FULL model_catalog (1,100+ rows, most `maintenance`/never probed) rather
   than the small working-models subset.

   Self-contained (fetches its own data via the `api` prop), same pattern as
   ./MarkupSection.tsx and ./PackagesSection.tsx.

   Server contract:
     GET  /api/admin/catalog/models                        (admin_catalog.py)
       -> [{ id, provider_model_id, provider, upstream, display_name,
              availability, provenance, context_window, currency,
              input_per_million, output_per_million,
              usd_input_per_million, usd_output_per_million,
              last_verified_at, markup_pct, public_id, audience,
              last_ok_at, health_status, health_last_error }]
       No query params -- the backend returns the entire catalog in one
       response. Pagination below is client-side over this single fetch;
       the table only ever *renders* one page of rows at a time.
     POST /api/admin/models/bulk-availability               (admin_catalog.py)
       <- { ids: string[], availability: 'available'|'degraded'|'maintenance'|'disabled' }
       -> { status, updated, availability }
     POST /api/admin/models/{model_id:path}/set-upstream     (admin_catalog.py)
       <- { upstream: string }  -> { status, model, upstream }
       Validated server-side against providers.configured_providers(); there
       is no endpoint that lists those names, so the datalist below only
       suggests upstream values already seen in the loaded catalog rows.
     POST /api/admin/models/{model_id:path}/toggle           (admin.py)
       -> { status, model, availability }  (flips available <-> disabled)
     POST /api/admin/models/{model_id:path}/test             (admin.py)
       -> { model, upstream, ok, latency_ms, error, status_code }
       No client-side timeout is applied (the shared `api()` helper in
       AdminPanel.tsx uses a plain `fetch` with no AbortController) --
       intentional, since a probe can legitimately take up to ~11s on a slow
       upstream router and has been observed at 103s for image generation.
       The server bounds it at 26s instead, under the Next.js rewrite's 30s
       ceiling, and RECORDS the result -- see
       backend/model_health_record.record_probe_sample.

   Product rule reminder (docs/NEXT-SESSION.md, CLAUDE.md): a model may only
   be served to real users after a successful *live* probe. Bulk-availability
   does not probe anything itself -- it is a raw availability flip -- so this
   UI never lets "available" be applied without a visible warning.

   DOM size: the table only ever maps over `pageRows` (filtered.slice at
   PAGE_SIZE=50), never over `rows`/`filtered` directly -- the tbody node
   count is bounded by the visible page (~50 rows), not by the catalog's
   ~1,196. Already windowed before this pass; nothing to fix here.

   Model ids: encodeURIComponent(id) is used for every :path route below.
   admin_catalog.py's own docstring says a `%2F` "never reaches Starlette's
   router as an encoded character" -- ASGI decodes percent-escapes into
   scope['path'] before routing, so a caller sending raw "/" or encoded
   "%2F" produces the identical scope['path'] and both match the `:path`
   converter the same way. encodeURIComponent is therefore both safe (it
   also correctly escapes any other reserved character an id might contain)
   and consistent with how AdminPanel.tsx already calls the sibling
   toggle/test routes.
   ═══════════════════════════════════════════════════════════════════════════ */

interface CatalogModelRow {
  id: string
  provider_model_id: string | null
  provider: string | null
  upstream: string | null
  display_name: string | null
  availability: string
  provenance: string | null
  context_window: number | null
  currency: string | null
  input_per_million: number | null
  output_per_million: number | null
  usd_input_per_million: number | null
  usd_output_per_million: number | null
  last_verified_at: string | null
  markup_pct: number | null
  public_id: string | null
  audience: string[] | null
  // Joined from model_health_state. `last_ok_at` is the ONLY truthful
  // "has this model ever answered" signal: last_verified_at above is NOT
  // NULL DEFAULT now() and every rollup touches it, so it reads as a
  // recent date for all ~1,200 rows including the never-probed ones.
  // services/probe_gate.py gates on last_ok_at, so the table shows it.
  last_ok_at: string | null
  health_status: string | null
  health_last_error: string | null
}

interface ModelOpsSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

const PAGE_SIZE = 50

export default function ModelOpsSection({ api }: ModelOpsSectionProps) {
  const lang = useLang()
  const s = modelOpsStrings(lang)
  const f = fmt(lang)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [rows, setRows] = useState<CatalogModelRow[]>([])

  const [search, setSearch] = useState('')
  const [availFilter, setAvailFilter] = useState<'all' | Availability>('all')
  // «سالم ولی پارک‌شده» is the view this whole pass exists to make possible:
  // rows with a confirmed live probe that are still not being served.
  const [probeFilter, setProbeFilter] = useState<ProbeFilter>('all')
  const [page, setPage] = useState(1)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkTarget, setBulkTarget] = useState<Availability>('available')
  const [bulkConfirming, setBulkConfirming] = useState(false)
  const [bulkSubmitting, setBulkSubmitting] = useState(false)

  const [busyId, setBusyId] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  // Only the most recently finished BULK run (not per-row retests below) --
  // BulkTestSummary reads this, separately from testResults, so a one-off
  // «تست زنده» click on a single row doesn't silently mutate the summary.
  const [lastBulkResults, setLastBulkResults] = useState<Record<string, TestResult> | null>(null)

  const [upstreamEditId, setUpstreamEditId] = useState<string | null>(null)
  const [upstreamDraft, setUpstreamDraft] = useState('')
  const [upstreamSaving, setUpstreamSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const res = await api('/api/admin/catalog/models')
      const data: CatalogModelRow[] = await res.json()
      setRows(Array.isArray(data) ? data : [])
    } catch (err) {
      setLoadError(errMessage(err, s.loadError))
    } finally {
      setLoading(false)
    }
  }, [api, s.loadError])

  const { bulkTest, run: runBulkTest, cancel: cancelBulkTest } = useBulkLiveTest({
    api,
    onResults: (results) => { setTestResults((prev) => ({ ...prev, ...results })); setLastBulkResults(results) },
    onDone: load,
  })

  useEffect(() => { load() }, [load])
  useEffect(() => { setPage(1) }, [search, availFilter, probeFilter])

  const counts = useMemo(() => {
    const c: Record<string, number> = { available: 0, degraded: 0, maintenance: 0, disabled: 0 }
    for (const r of rows) c[r.availability] = (c[r.availability] || 0) + 1
    return c
  }, [rows])

  /* The number the owner actually needs and could not see anywhere: how
     many models have a confirmed live probe, and how many of those are
     healthy-but-parked. A live sweep of the parked catalog on 2026-08-25
     found 192 of 1,155 answering — against 28 being served. */
  const probeCounts = useMemo(() => {
    let confirmed = 0, parkedConfirmed = 0, ready = 0
    for (const r of rows) {
      if (!r.last_ok_at) continue
      confirmed += 1
      if (r.availability !== 'available') parkedConfirmed += 1
      if ((r.input_per_million || 0) > 0 && r.public_id) ready += 1
    }
    return { confirmed, parkedConfirmed, ready }
  }, [rows])

  const upstreamSuggestions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.upstream).filter((u): u is string => !!u))),
    [rows],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (availFilter !== 'all' && r.availability !== availFilter) return false
      if (probeFilter === 'confirmed' && !r.last_ok_at) return false
      if (probeFilter === 'unprobed' && r.last_ok_at) return false
      // «آمادهٔ ارائه»: everything the server checks before a model can
      // actually reach a user -- a confirmed probe, a price, and a public_id.
      // A row can be «در دسترس» and still be invisible without the last one.
      if (probeFilter === 'ready' && !(r.last_ok_at && (r.input_per_million || 0) > 0 && r.public_id)) return false
      if (!q) return true
      return (
        r.id.toLowerCase().includes(q) ||
        (r.display_name || '').toLowerCase().includes(q) ||
        (r.provider_model_id || '').toLowerCase().includes(q) ||
        (r.provider || '').toLowerCase().includes(q) ||
        (r.upstream || '').toLowerCase().includes(q)
      )
    })
  }, [rows, search, availFilter, probeFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const pageAllSelected = pageRows.length > 0 && pageRows.every((r) => selected.has(r.id))

  const toggleSelect = (id: string) => setSelected((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })
  const togglePageAll = () => setSelected((prev) => {
    const next = new Set(prev)
    if (pageAllSelected) { for (const r of pageRows) next.delete(r.id) } else { for (const r of pageRows) next.add(r.id) }
    return next
  })
  const selectAllFiltered = () => setSelected(new Set(filtered.map((r) => r.id)))
  const clearSelection = () => setSelected(new Set())

  const openBulkConfirm = () => {
    if (selected.size === 0) { toast(s.selectAtLeastOne, 'error'); return }
    setBulkConfirming(true)
  }

  const applyBulk = async () => {
    setBulkSubmitting(true)
    try {
      const res = await api('/api/admin/models/bulk-availability', {
        method: 'POST',
        body: JSON.stringify({ ids: Array.from(selected), availability: bulkTarget }),
      })
      const body = await res.json()
      toast(s.bulkApplied(f.num(body.updated ?? selected.size), availabilityLabel(bulkTarget, lang)), 'success')
      setBulkConfirming(false)
      clearSelection()
      await load()
    } catch (err) {
      // The server now refuses any transition to 'available' for a model
      // that has never had a successful live probe, and names the rejected
      // model ids in the 400 `detail` -- errMessage surfaces that verbatim
      // instead of a generic "failed" toast that hides which models to fix.
      toast(errMessage(err, s.bulkFailed), 'error')
    } finally {
      setBulkSubmitting(false)
    }
  }

  const toggleOne = async (id: string) => {
    setBusyId(id)
    try {
      await api(`/api/admin/models/${encodeURIComponent(id)}/toggle`, { method: 'POST' })
      toast(s.toggleSuccess, 'success')
      await load()
    } catch (err) {
      toast(errMessage(err, s.toggleFailed), 'error')
    } finally {
      setBusyId(null)
    }
  }

  const testOne = async (id: string) => {
    setTestingId(id)
    try {
      const res = await api(`/api/admin/models/${encodeURIComponent(id)}/test`, { method: 'POST' })
      const body = await res.json()
      setTestResults((prev) => ({ ...prev, [id]: { ok: !!body.ok, latency_ms: body.latency_ms ?? null, error: body.error ?? null, status_code: body.status_code ?? null } }))
      toast(body.ok ? s.testSuccess(f.num(body.latency_ms)) : s.testFailed(body.error || s.unknownError), body.ok ? 'success' : 'error')
    } catch (err) {
      toast(errMessage(err, s.testFailedGeneric), 'error')
    } finally {
      setTestingId(null)
    }
  }

  const openUpstreamEdit = (row: CatalogModelRow) => { setUpstreamEditId(row.id); setUpstreamDraft(row.upstream || '') }
  const saveUpstream = async (id: string) => {
    const upstream = upstreamDraft.trim()
    if (!upstream) { toast(s.upstreamEmpty, 'error'); return }
    setUpstreamSaving(true)
    try {
      await api(`/api/admin/models/${encodeURIComponent(id)}/set-upstream`, { method: 'POST', body: JSON.stringify({ upstream }) })
      toast(s.upstreamSaved, 'success')
      setUpstreamEditId(null)
      await load()
    } catch (err) {
      toast(errMessage(err, s.upstreamFailed), 'error')
    } finally {
      setUpstreamSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title={s.title}
        subtitle={s.subtitle(f.num(rows.length), f.num(counts.available || 0))}
      />

      <div className="admin-card" style={{ borderRight: '3px solid var(--warning, #f59e0b)' }}>
        <p className="text-xs" style={{ color: 'var(--warning, #f59e0b)' }}>
          <Icon name="warning" size={12} /> {s.warning1}{' '}
          {s.warning2}
        </p>
      </div>

      <CatalogFilterBar
        search={search} onSearch={setSearch}
        availFilter={availFilter} onAvailFilter={setAvailFilter}
        probeFilter={probeFilter} onProbeFilter={setProbeFilter}
        onReload={load} loading={loading}
        matched={filtered.length} total={rows.length}
        counts={counts} probeCounts={probeCounts}
      />

      <BulkActionBar
        selectedCount={selected.size}
        filteredCount={filtered.length}
        pageAllSelected={pageAllSelected}
        testRunning={bulkTest !== null}
        target={bulkTarget}
        onTarget={setBulkTarget}
        onSelectAllFiltered={selectAllFiltered}
        onTogglePage={togglePageAll}
        onClearSelection={clearSelection}
        onOpenConfirm={openBulkConfirm}
        onRunTest={() => runBulkTest(Array.from(selected))}
      />

      {bulkTest && <BulkLiveTestProgress state={bulkTest} onCancel={cancelBulkTest} />}
      {!bulkTest && lastBulkResults && <BulkTestSummary results={lastBulkResults} api={api} onDone={load} />}

      <div className="admin-card">
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="p-3"><input type="checkbox" checked={pageAllSelected} onChange={togglePageAll} /></th>
                <th className="p-3">{s.colModel}</th>
                <th className="p-3">{s.colStatus}</th>
                <th className="p-3">{s.colProvider}</th>
                <th className="p-3">{s.colContext}</th>
                <th className="p-3">{s.colPrice}</th>
                {/* Was `last_verified_at`, which showed a recent date for
                    every row in the catalog including the ~1,155 that had
                    never been probed once -- the column is NOT NULL DEFAULT
                    now() and the rollup touches it every pass. This one
                    reads model_health_state.last_ok_at, the same column
                    the server's enable-gate checks. */}
                <th className="p-3">{s.colProbe}</th>
                <th className="p-3">{s.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">{s.loadingRow}</td></tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={8} className="p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
                    {loadError}{' '}
                    <button className="underline" onClick={load}>{s.retry}</button>
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">{s.noModelsFound}</td></tr>
              ) : (
                pageRows.map((r) => {
                  const avail = (AVAILABILITY_OPTIONS as readonly string[]).includes(r.availability) ? (r.availability as Availability) : 'maintenance'
                  const tr = testResults[r.id]
                  return (
                    <tr key={r.id}>
                      <td className="p-3"><input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} /></td>
                      <td className="p-3">
                        <div className="font-medium text-primary">{r.display_name || r.id}</div>
                        <div className="text-xs font-mono text-muted" dir="ltr">{r.id}</div>
                      </td>
                      <td className="p-3">
                        <span className="text-xs px-2 py-1 rounded-full" style={{ background: `${AVAILABILITY_COLOR[avail]}15`, color: AVAILABILITY_COLOR[avail] }}>
                          {availabilityLabel(avail, lang)}
                        </span>
                        {TOGGLEABLE.has(avail) ? (
                          <button className="btn btn-sm mt-1" style={{ display: 'block' }} onClick={() => toggleOne(r.id)} disabled={busyId === r.id}>
                            {busyId === r.id ? '...' : (avail === 'available' ? s.disableAction : s.enableAction)}
                          </button>
                        ) : (
                          <div className="text-xs text-muted mt-1" title={s.toggleHint}>
                            {s.useBulkInstead}
                          </div>
                        )}
                      </td>
                      <td className="p-3">
                        <div className="text-xs text-muted" dir="ltr">{r.provider || '—'}</div>
                        {upstreamEditId === r.id ? (
                          <div className="flex items-center gap-1 mt-1">
                            <input
                              className="input" style={{ maxWidth: 150 }} dir="ltr" list="model-ops-upstream-suggestions"
                              value={upstreamDraft} onChange={(e) => setUpstreamDraft(e.target.value)}
                            />
                            <button className="btn btn-sm" onClick={() => saveUpstream(r.id)} disabled={upstreamSaving}><Icon name="check" size={12} /></button>
                            <button className="btn btn-sm" onClick={() => setUpstreamEditId(null)} disabled={upstreamSaving}><Icon name="close" size={12} /></button>
                          </div>
                        ) : (
                          <button className="text-xs underline mt-1" dir="ltr" onClick={() => openUpstreamEdit(r)} title={s.changeUpstreamTitle}>
                            {r.upstream || '—'}
                          </button>
                        )}
                      </td>
                      <td className="p-3 text-xs">{r.context_window ? f.num(r.context_window) : '—'}</td>
                      <td className="p-3 text-xs">
                        <div>{f.price(r.input_per_million)}</div>
                        <div className="text-muted">{f.price(r.output_per_million)}</div>
                      </td>
                      <td className="p-3 text-xs">
                        {r.last_ok_at ? (
                          <>
                            <span style={{ color: AVAILABILITY_COLOR.available }}>{f.date(r.last_ok_at)}</span>
                            {r.availability !== 'available' && (
                              <div className="text-[10px] text-muted">{s.healthyUnserved}</div>
                            )}
                            {!r.public_id && (
                              <div className="text-[10px] text-muted">{s.noPublicId}</div>
                            )}
                          </>
                        ) : (
                          <>
                            <span className="text-muted">{s.never}</span>
                            {/* The reason, not just the verdict: 298 of the
                                failures in the last full sweep were "no
                                active credentials for provider", which is
                                an upstream account problem the owner can
                                fix -- and looks identical to a dead model
                                if only the verdict is shown. */}
                            {r.health_last_error && (
                              <div className="text-[10px] font-mono text-muted" dir="ltr">{r.health_last_error}</div>
                            )}
                          </>
                        )}
                      </td>
                      <td className="p-3">
                        <button className="btn btn-sm" onClick={() => testOne(r.id)} disabled={testingId === r.id}>
                          {testingId === r.id ? (
                            <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                          ) : s.testLive}
                        </button>
                        {tr && (
                          <div className="text-xs mt-1" style={{ color: tr.ok ? AVAILABILITY_COLOR.available : AVAILABILITY_COLOR.disabled }}>
                            {tr.ok ? s.healthyLatency(f.num(tr.latency_ms)) : (tr.error || s.errorFallback)}
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <datalist id="model-ops-upstream-suggestions">
          {upstreamSuggestions.map((u) => <option key={u} value={u} />)}
        </datalist>

        {!loading && !loadError && filtered.length > 0 && (
          <div className="flex items-center justify-between mt-3 text-xs text-muted">
            <span>{s.pageOf(f.num(page), f.num(totalPages))}</span>
            <div className="flex gap-2">
              <button className="btn btn-sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>{s.prev}</button>
              <button className="btn btn-sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>{s.next}</button>
            </div>
          </div>
        )}
      </div>

      {bulkConfirming && (
        <BulkConfirmModal
          count={selected.size}
          target={bulkTarget}
          submitting={bulkSubmitting}
          onApply={applyBulk}
          onClose={() => setBulkConfirming(false)}
        />
      )}

    </div>
  )
}
