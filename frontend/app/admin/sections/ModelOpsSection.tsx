'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice, faDate } from '@/lib/format'
import { SectionHeader, StatCard } from './shared'
import { errMessage } from '../api'
import { AVAILABILITY_OPTIONS, AVAILABILITY_FA, AVAILABILITY_COLOR, TOGGLEABLE, type Availability } from './availability'

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
       The server bounds it instead: admin_pricing._ADMIN_PROBE_BUDGET_S caps
       the probe plus its retry at 26s, under the 30s ceiling of the Next.js
       rewrite this call travels through.
       This route now RECORDS its result. It used to only display it, which
       made the panel's advice ("run a live test first, or the server will
       refuse to enable it") impossible to follow — see
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

interface TestResult {
  ok: boolean
  latency_ms: number | null
  error: string | null
  status_code: number | null
}

interface ModelOpsSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}


// POST /admin/models/{id}/toggle (admin.py) only flips between these two --
// it 400s on 'degraded'/'maintenance'. Same set PricingSection.tsx enforces
// for the same endpoint; a clickable button on a row this call rejects
// used to be a guaranteed failed request on 1,155 of 1,200 live rows.

const PAGE_SIZE = 50

/* Bulk «تست زنده».
 *
 * Deliberately NOT a new bulk endpoint. Each model is one call to the
 * existing per-model /test route, because that route's whole job is to spend
 * up to ~26s on one upstream, and the browser reaches the API through a
 * Next.js rewrite that hard-caps at 30s. A server-side bulk probe of even
 * ten models could not answer inside that cap; a hundred calls of one model
 * each always can, and the admin gets a live count instead of a spinner that
 * either returns in twenty minutes or 500s.
 *
 * The concurrency is small on purpose: these probes go to the same three
 * upstream routers the site serves traffic through, and the failure this
 * whole feature exists to fix — «All credentials are cooling down» — is a
 * rate limit. Testing faster produces more cooldowns, not more answers. */
const BULK_TEST_CONCURRENCY = 3

/** Above this, a bulk run is long enough that the admin should be told the
 *  rough cost in time before starting it rather than after. At 3 at a time
 *  and a few seconds each, 200 models is already several minutes. */
const BULK_TEST_WARN_ABOVE = 200

interface BulkTestState {
  total: number
  done: number
  ok: number
  cancel: boolean
}

export default function ModelOpsSection({ api }: ModelOpsSectionProps) {
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [rows, setRows] = useState<CatalogModelRow[]>([])

  const [search, setSearch] = useState('')
  const [availFilter, setAvailFilter] = useState<'all' | Availability>('all')
  // «سالم ولی پارک‌شده» is the view this whole pass exists to make possible:
  // rows with a confirmed live probe that are still not being served.
  const [probeFilter, setProbeFilter] = useState<'all' | 'confirmed' | 'unprobed' | 'ready'>('all')
  const [page, setPage] = useState(1)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkTarget, setBulkTarget] = useState<Availability>('available')
  const [bulkConfirming, setBulkConfirming] = useState(false)
  const [bulkSubmitting, setBulkSubmitting] = useState(false)

  const [busyId, setBusyId] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [bulkTest, setBulkTest] = useState<BulkTestState | null>(null)
  // The live, mutable run object. `bulkTest` is a render-only snapshot of
  // it, so «توقف» has to reach through this to actually stop the workers.
  const bulkRunRef = useRef<BulkTestState | null>(null)

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
      setLoadError(errMessage(err, 'خطا در دریافت فهرست کاتالوگ — اتصال یا سرور مشکل دارد.'))
    } finally {
      setLoading(false)
    }
  }, [api])

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
    if (selected.size === 0) { toast('ابتدا حداقل یک مدل را انتخاب کنید', 'error'); return }
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
      toast(`وضعیت ${faNum(body.updated ?? selected.size)} مدل به «${AVAILABILITY_FA[bulkTarget]}» تغییر کرد`, 'success')
      setBulkConfirming(false)
      clearSelection()
      await load()
    } catch (err) {
      // The server now refuses any transition to 'available' for a model
      // that has never had a successful live probe, and names the rejected
      // model ids in the 400 `detail` -- errMessage surfaces that verbatim
      // instead of a generic "failed" toast that hides which models to fix.
      toast(errMessage(err, 'اعمال گروهی ناموفق بود'), 'error')
    } finally {
      setBulkSubmitting(false)
    }
  }

  const toggleOne = async (id: string) => {
    setBusyId(id)
    try {
      await api(`/api/admin/models/${encodeURIComponent(id)}/toggle`, { method: 'POST' })
      toast('وضعیت مدل تغییر کرد', 'success')
      await load()
    } catch (err) {
      toast(errMessage(err, 'تغییر وضعیت ناموفق بود'), 'error')
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
      toast(body.ok ? `تست موفق — تأخیر ${faNum(body.latency_ms)} میلی‌ثانیه` : `تست ناموفق: ${body.error || 'خطای نامشخص'}`, body.ok ? 'success' : 'error')
    } catch (err) {
      toast(errMessage(err, 'اجرای تست انجام نشد (خطای شبکه یا سرور)'), 'error')
    } finally {
      setTestingId(null)
    }
  }

  const runBulkTest = async () => {
    const ids = Array.from(selected)
    if (ids.length === 0) { toast('ابتدا حداقل یک مدل را انتخاب کنید', 'error'); return }
    if (ids.length > BULK_TEST_WARN_ABOVE) {
      const minutes = Math.ceil((ids.length * 4) / BULK_TEST_CONCURRENCY / 60)
      if (!window.confirm(
        `${ids.length} مدل انتخاب شده است. تست زندهٔ همهٔ آن‌ها حدود ${minutes} دقیقه طول می‌کشد `
        + 'و در همین صفحه اجرا می‌شود (با بستن صفحه متوقف می‌شود). ادامه می‌دهید؟',
      )) return
    }

    // `state` is the mutable source of truth for the run; the useState copy
    // below is only for rendering. Reading progress out of React state
    // inside the workers would read a stale snapshot on every tick.
    const state: BulkTestState = { total: ids.length, done: 0, ok: 0, cancel: false }
    bulkRunRef.current = state
    setBulkTest({ ...state })

    const results: Record<string, TestResult> = {}
    let cursor = 0
    const worker = async () => {
      while (!state.cancel) {
        const i = cursor++
        if (i >= ids.length) return
        const id = ids[i]
        try {
          const res = await api(`/api/admin/models/${encodeURIComponent(id)}/test`, { method: 'POST' })
          const body = await res.json()
          results[id] = {
            ok: !!body.ok, latency_ms: body.latency_ms ?? null,
            error: body.error ?? null, status_code: body.status_code ?? null,
          }
          if (body.ok) state.ok += 1
        } catch (err) {
          // One unreachable model must not abort the other 199. The reason
          // is kept per-row so the admin can see WHICH failed and why.
          results[id] = { ok: false, latency_ms: null, error: errMessage(err, 'خطای شبکه'), status_code: null }
        } finally {
          state.done += 1
          setBulkTest({ ...state })
        }
      }
    }

    await Promise.all(Array.from({ length: Math.min(BULK_TEST_CONCURRENCY, ids.length) }, worker))
    setTestResults((prev) => ({ ...prev, ...results }))
    bulkRunRef.current = null
    setBulkTest(null)
    toast(
      state.cancel
        ? `تست متوقف شد — ${faNum(state.ok)} مدل سالم از ${faNum(state.done)} مدل آزموده‌شده`
        : `${faNum(state.ok)} مدل از ${faNum(state.total)} مدل سالم بود`,
      state.ok > 0 ? 'success' : 'error',
    )
    // The catalog carries last_verified_at, which every probe moves.
    await load()
  }

  const openUpstreamEdit = (row: CatalogModelRow) => { setUpstreamEditId(row.id); setUpstreamDraft(row.upstream || '') }
  const saveUpstream = async (id: string) => {
    const upstream = upstreamDraft.trim()
    if (!upstream) { toast('نام upstream نمی‌تواند خالی باشد', 'error'); return }
    setUpstreamSaving(true)
    try {
      await api(`/api/admin/models/${encodeURIComponent(id)}/set-upstream`, { method: 'POST', body: JSON.stringify({ upstream }) })
      toast('upstream این مدل تغییر کرد', 'success')
      setUpstreamEditId(null)
      await load()
    } catch (err) {
      toast(errMessage(err, 'تغییر upstream ناموفق بود — نام باید یکی از تأمین‌کننده‌های پیکربندی‌شده باشد'), 'error')
    } finally {
      setUpstreamSaving(false)
    }
  }

  return (
    <div className="space-y-6" dir="rtl">
      <SectionHeader
        title="عملیات کاتالوگ مدل‌ها"
        subtitle={`${faNum(rows.length)} ردیف کاتالوگ — تنها ${faNum(counts.available || 0)} مورد «در دسترس»`}
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon="chart" label="در دسترس" value={faNum(counts.available || 0)} color={AVAILABILITY_COLOR.available} />
        <StatCard icon="warning" label="کاهش‌یافته" value={faNum(counts.degraded || 0)} color={AVAILABILITY_COLOR.degraded} />
        <StatCard icon="clock" label="در تعمیر" value={faNum(counts.maintenance || 0)} color={AVAILABILITY_COLOR.maintenance} />
        <StatCard icon="close" label="غیرفعال" value={faNum(counts.disabled || 0)} color={AVAILABILITY_COLOR.disabled} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard icon="check" label="پروب زندهٔ تأییدشده" value={faNum(probeCounts.confirmed)} color={AVAILABILITY_COLOR.available} />
        <StatCard icon="clock" label="سالم ولی ارائه‌نشده" value={faNum(probeCounts.parkedConfirmed)} color={AVAILABILITY_COLOR.degraded} />
        <StatCard icon="chart" label="آمادهٔ ارائه" value={faNum(probeCounts.ready)} color={AVAILABILITY_COLOR.available} />
      </div>

      <div className="admin-card" style={{ borderRight: '3px solid var(--warning, #f59e0b)' }}>
        <p className="text-xs" style={{ color: 'var(--warning, #f59e0b)' }}>
          <Icon name="warning" size={12} /> سرور اجازهٔ «در دسترس» کردن مدلی که هرگز «تست زنده» موفق نداشته را نمی‌دهد و این درخواست را با نام همان مدل‌ها رد می‌کند.
          مدل‌ها را انتخاب کنید و «تست زندهٔ گروهی» را بزنید؛ هر تست موفق همان‌جا ثبت می‌شود و مدل را برای فعال‌سازی واجد شرایط می‌کند.
        </p>
      </div>

      <div className="admin-card flex flex-wrap items-center gap-3">
        <input className="input" placeholder="جستجو در نام، شناسه، تأمین‌کننده…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ minWidth: 220 }} />
        <select className="input" value={availFilter} onChange={(e) => setAvailFilter(e.target.value as 'all' | Availability)} style={{ maxWidth: 170 }}>
          <option value="all">همهٔ وضعیت‌ها</option>
          {AVAILABILITY_OPTIONS.map((a) => <option key={a} value={a}>{AVAILABILITY_FA[a]}</option>)}
        </select>
        <select className="input" value={probeFilter} onChange={(e) => setProbeFilter(e.target.value as typeof probeFilter)} style={{ maxWidth: 190 }}>
          <option value="all">همهٔ مدل‌ها</option>
          <option value="confirmed">پروب تأییدشده</option>
          <option value="unprobed">بدون پروب موفق</option>
          <option value="ready">آمادهٔ ارائه (پروب + قیمت + شناسهٔ عمومی)</option>
        </select>
        <button className="btn btn-sm" onClick={load} disabled={loading}>
          <Icon name="refresh" size={14} /> بازخوانی
        </button>
        <span className="text-xs text-muted">{faNum(filtered.length)} از {faNum(rows.length)} مدل مطابق فیلتر</span>
      </div>

      <div className="admin-card flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium text-primary">{faNum(selected.size)} مدل انتخاب شده</span>
        <button className="btn btn-sm" onClick={selectAllFiltered}>انتخاب همهٔ {faNum(filtered.length)} مورد فیلترشده</button>
        <button className="btn btn-sm" onClick={togglePageAll}>{pageAllSelected ? 'لغو انتخاب این صفحه' : 'انتخاب این صفحه'}</button>
        <button className="btn btn-sm" onClick={clearSelection} disabled={selected.size === 0}>پاک کردن انتخاب</button>
        <span className="text-xs text-muted">تغییر گروهی وضعیت به:</span>
        <select className="input" value={bulkTarget} onChange={(e) => setBulkTarget(e.target.value as Availability)} style={{ maxWidth: 160 }}>
          {AVAILABILITY_OPTIONS.map((a) => <option key={a} value={a}>{AVAILABILITY_FA[a]}</option>)}
        </select>
        <button className="btn btn-sm" onClick={openBulkConfirm} disabled={selected.size === 0 || bulkTest !== null}>
          <Icon name="check" size={14} /> اعمال گروهی
        </button>
        <button className="btn btn-sm" onClick={runBulkTest} disabled={selected.size === 0 || bulkTest !== null}>
          <Icon name="refresh" size={14} /> تست زندهٔ گروهی
        </button>
      </div>

      {bulkTest && (
        <div className="admin-card flex flex-wrap items-center gap-3"
             style={{ borderRight: '3px solid var(--accent, #6366f1)' }}>
          <span className="w-4 h-4 border-2 rounded-full animate-spin inline-block shrink-0"
                style={{ borderColor: 'var(--border)', borderTopColor: 'var(--accent, #6366f1)' }} />
          <span className="text-sm text-primary">
            در حال تست زنده: {faNum(bulkTest.done)} از {faNum(bulkTest.total)} — {faNum(bulkTest.ok)} مدل سالم
          </span>
          {/* Progress is a plain div, not a chart: recharts breaks the build
              (documented in AdminCharts.tsx). */}
          <div className="h-1 rounded flex-1" style={{ minWidth: 120, background: 'var(--border)' }}>
            <div className="h-1 rounded" style={{
              width: `${Math.round((bulkTest.done / Math.max(1, bulkTest.total)) * 100)}%`,
              background: 'var(--accent, #6366f1)',
            }} />
          </div>
          {/* The ref, not the state copy: `bulkTest` is a snapshot spread out
              of the run object for rendering, so flipping ITS `cancel` would
              stop nothing. The workers poll the ref. */}
          <button className="btn btn-sm" onClick={() => {
            if (bulkRunRef.current) bulkRunRef.current.cancel = true
            setBulkTest((prev) => (prev ? { ...prev, cancel: true } : prev))
          }}>
            توقف
          </button>
        </div>
      )}

      <div className="admin-card">
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="p-3"><input type="checkbox" checked={pageAllSelected} onChange={togglePageAll} /></th>
                <th className="text-right p-3">مدل</th>
                <th className="text-right p-3">وضعیت</th>
                <th className="text-right p-3">تأمین‌کننده / upstream</th>
                <th className="text-right p-3">پنجرهٔ متن</th>
                <th className="text-right p-3">قیمت (ورودی / خروجی هر میلیون)</th>
                {/* Was `last_verified_at`, which showed a recent date for
                    every row in the catalog including the ~1,155 that had
                    never been probed once -- the column is NOT NULL DEFAULT
                    now() and the rollup touches it every pass. This one
                    reads model_health_state.last_ok_at, the same column
                    the server's enable-gate checks. */}
                <th className="text-right p-3">پروب زندهٔ موفق</th>
                <th className="text-right p-3">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">در حال بارگذاری…</td></tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={8} className="p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
                    {loadError}{' '}
                    <button className="underline" onClick={load}>تلاش دوباره</button>
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">مدلی با این فیلتر یافت نشد</td></tr>
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
                          {AVAILABILITY_FA[avail]}
                        </span>
                        {TOGGLEABLE.has(avail) ? (
                          <button className="btn btn-sm mt-1" style={{ display: 'block' }} onClick={() => toggleOne(r.id)} disabled={busyId === r.id}>
                            {busyId === r.id ? '...' : (avail === 'available' ? 'غیرفعال کن' : 'در دسترس کن')}
                          </button>
                        ) : (
                          <div className="text-xs text-muted mt-1" title="این کلید سریع فقط بین «در دسترس» و «غیرفعال» جابه‌جا می‌کند">
                            برای این وضعیت، از «تغییر گروهی» در بالای صفحه استفاده کنید
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
                          <button className="text-xs underline mt-1" dir="ltr" onClick={() => openUpstreamEdit(r)} title="تغییر upstream">
                            {r.upstream || '—'}
                          </button>
                        )}
                      </td>
                      <td className="p-3 text-xs">{r.context_window ? faNum(r.context_window) : '—'}</td>
                      <td className="p-3 text-xs">
                        <div>{faPrice(r.input_per_million)}</div>
                        <div className="text-muted">{faPrice(r.output_per_million)}</div>
                      </td>
                      <td className="p-3 text-xs">
                        {r.last_ok_at ? (
                          <>
                            <span style={{ color: AVAILABILITY_COLOR.available }}>{faDate(r.last_ok_at)}</span>
                            {r.availability !== 'available' && (
                              <div className="text-[10px] text-muted">سالم ولی ارائه‌نشده</div>
                            )}
                            {!r.public_id && (
                              <div className="text-[10px] text-muted">بدون شناسهٔ عمومی — برای کاربر دیده نمی‌شود</div>
                            )}
                          </>
                        ) : (
                          <>
                            <span className="text-muted">هرگز</span>
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
                          ) : 'تست زنده'}
                        </button>
                        {tr && (
                          <div className="text-xs mt-1" style={{ color: tr.ok ? AVAILABILITY_COLOR.available : AVAILABILITY_COLOR.disabled }}>
                            {tr.ok ? `سالم — ${faNum(tr.latency_ms)}ms` : (tr.error || 'خطا')}
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
            <span>صفحهٔ {faNum(page)} از {faNum(totalPages)}</span>
            <div className="flex gap-2">
              <button className="btn btn-sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>قبلی</button>
              <button className="btn btn-sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>بعدی</button>
            </div>
          </div>
        )}
      </div>

      {bulkConfirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => !bulkSubmitting && setBulkConfirming(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="card relative w-full max-w-md" dir="rtl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-primary">تأیید تغییر گروهی وضعیت</h3>
              <button className="btn btn-icon btn-sm" onClick={() => setBulkConfirming(false)} disabled={bulkSubmitting}><Icon name="close" size={16} /></button>
            </div>
            <p className="text-sm">
              وضعیت <span className="font-bold">{faNum(selected.size)}</span> مدل به «<span className="font-bold">{AVAILABILITY_FA[bulkTarget]}</span>» تغییر می‌کند.
            </p>
            {bulkTarget === 'available' && (
              <p className="text-xs mt-2 flex items-center gap-1" style={{ color: 'var(--warning, #f59e0b)' }}>
                <Icon name="warning" size={12} /> سرور مدل‌هایی که «تست زنده» موفق نداشته‌اند را رد می‌کند — اگر برخی از انتخاب‌ها هنوز تست نشده باشند، این عملیات با خطا و نام همان مدل‌ها برمی‌گردد.
              </p>
            )}
            <div className="flex gap-2 mt-5">
              <button className="btn flex-1" onClick={applyBulk} disabled={bulkSubmitting}>{bulkSubmitting ? 'در حال اعمال...' : 'تأیید و اعمال'}</button>
              <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => setBulkConfirming(false)} disabled={bulkSubmitting}>انصراف</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
