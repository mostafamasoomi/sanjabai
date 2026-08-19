'use client'

import { useState, useEffect, useMemo, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { toast } from '@/components/ui'

/* ═══════════════════════════════════════════════════════════════════════════
   Models tab — full catalog management surface.

   Loaded once via GET /api/admin/catalog/models (server-authoritative,
   admin-only — includes provider/upstream, which end users must never see).
   Search / filter / sort / pagination all run client-side against that one
   in-memory array: at ~1,123 rows and a dozen short fields each the payload
   is a few hundred KB, so filtering it in JS is sub-millisecond — cheaper
   and more responsive than round-tripping to the server on every keystroke,
   and it matches how the pricing tab already loads its full model list in
   one shot. Pagination here is purely a rendering slice, not a re-fetch.
   ═══════════════════════════════════════════════════════════════════════════ */

interface CatalogModelRow {
  id: string
  provider_model_id: string
  provider: string
  upstream: string | null
  display_name: string
  availability: 'available' | 'degraded' | 'maintenance' | 'disabled'
  provenance: string
  context_window: number
  currency: string
  input_per_million: number
  output_per_million: number
  usd_input_per_million: number | null
  usd_output_per_million: number | null
  last_verified_at: string | null
}

interface TestResult {
  ok: boolean
  latency_ms: number
  error: string | null
}

const PAGE_SIZE = 50

// Encode each path segment separately so a literal '/' inside a model id
// (most of them have one, e.g. freellmapi/agnes-1.5-flash) survives as an
// actual path separator instead of becoming an inert %2F.
function encodeModelPath(id: string): string {
  return id.split('/').map(encodeURIComponent).join('/')
}

const AVAILABILITY_FA: Record<string, string> = {
  available: 'فعال', degraded: 'کاهش‌یافته', maintenance: 'تعمیرات', disabled: 'غیرفعال',
}
const AVAILABILITY_BADGE: Record<string, string> = {
  available: 'badge-positive', degraded: 'badge-warning', maintenance: 'badge-accent', disabled: 'badge-danger',
}

export default function ModelsTab({ api }: { api: (path: string, opts?: RequestInit) => Promise<Response> }) {
  const [rows, setRows] = useState<CatalogModelRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [providerFilter, setProviderFilter] = useState('')
  const [upstreamFilter, setUpstreamFilter] = useState('')
  const [availabilityFilter, setAvailabilityFilter] = useState('')
  const [page, setPage] = useState(1)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkConfirm, setBulkConfirm] = useState<'available' | 'disabled' | null>(null)
  const [bulkBusy, setBulkBusy] = useState(false)

  const [busyId, setBusyId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})

  const [editRow, setEditRow] = useState<CatalogModelRow | null>(null)
  const [editIn, setEditIn] = useState('')
  const [editOut, setEditOut] = useState('')
  const [editSaving, setEditSaving] = useState(false)

  const [upstreamRow, setUpstreamRow] = useState<CatalogModelRow | null>(null)
  const [upstreamValue, setUpstreamValue] = useState('')
  const [upstreamSaving, setUpstreamSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await api('/api/admin/catalog/models')
      const d = await r.json()
      setRows(Array.isArray(d) ? d : [])
    } catch {
      setError('خطا در بارگذاری کاتالوگ مدل‌ها')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  const providers = useMemo(() => Array.from(new Set(rows.map((r) => r.provider))).sort(), [rows])
  const upstreams = useMemo(
    () => Array.from(new Set(rows.map((r) => r.upstream).filter((u): u is string => !!u))).sort(),
    [rows],
  )
  const byDisplayName = useMemo(() => {
    const m = new Map<string, CatalogModelRow[]>()
    for (const r of rows) {
      const list = m.get(r.display_name) || []
      list.push(r)
      m.set(r.display_name, list)
    }
    return m
  }, [rows])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (q && !r.id.toLowerCase().includes(q) && !r.display_name.toLowerCase().includes(q)) return false
      if (providerFilter && r.provider !== providerFilter) return false
      if (upstreamFilter && r.upstream !== upstreamFilter) return false
      if (availabilityFilter && r.availability !== availabilityFilter) return false
      return true
    })
  }, [rows, search, providerFilter, upstreamFilter, availabilityFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageSafe = Math.min(page, totalPages)
  const pageRows = filtered.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE)

  // Reset to page 1 whenever the filtered set changes shape.
  useEffect(() => { setPage(1) }, [search, providerFilter, upstreamFilter, availabilityFilter])

  const resetFilters = () => {
    setSearch(''); setProviderFilter(''); setUpstreamFilter(''); setAvailabilityFilter('')
  }

  // ─── Selection ────────────────────────────────────────────────────────
  const pageIds = pageRows.map((r) => r.id)
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id))
  const toggleSelectAllPage = () => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (allPageSelected) pageIds.forEach((id) => next.delete(id))
      else pageIds.forEach((id) => next.add(id))
      return next
    })
  }
  const toggleSelectOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const clearSelection = () => { setSelected(new Set()); setBulkConfirm(null) }

  // ─── Per-row actions ──────────────────────────────────────────────────
  const applyAvailability = (ids: string[], availability: string) => {
    setRows((prev) => prev.map((r) => (ids.includes(r.id) ? { ...r, availability: availability as CatalogModelRow['availability'] } : r)))
  }

  const toggleOne = async (row: CatalogModelRow) => {
    setBusyId(row.id)
    try {
      const r = await api(`/api/admin/models/${encodeURIComponent(row.id)}/toggle`, { method: 'POST' })
      const data = await r.json()
      applyAvailability([row.id], data.availability)
      toast(data.availability === 'available' ? `${row.display_name} فعال شد` : `${row.display_name} غیرفعال شد`, 'success')
    } catch {
      toast('خطا در تغییر وضعیت مدل', 'error')
    } finally {
      setBusyId(null)
    }
  }

  const testOne = async (row: CatalogModelRow) => {
    setBusyId(row.id)
    try {
      const r = await api(`/api/admin/models/${encodeURIComponent(row.id)}/test`, { method: 'POST' })
      const data = await r.json()
      setTestResults((prev) => ({ ...prev, [row.id]: data }))
      toast(data.ok ? `${row.display_name} پاسخ داد (${data.latency_ms}ms)` : `${row.display_name} پاسخ نداد: ${data.error || 'نامشخص'}`, data.ok ? 'success' : 'error')
    } catch {
      toast('خطا در تست مدل', 'error')
    } finally {
      setBusyId(null)
    }
  }

  const openEdit = (row: CatalogModelRow) => {
    setEditRow(row); setEditIn(String(row.input_per_million)); setEditOut(String(row.output_per_million))
  }
  const saveEdit = async () => {
    if (!editRow) return
    setEditSaving(true)
    try {
      await api('/api/admin/pricing', {
        method: 'POST',
        body: JSON.stringify({ model: editRow.id, input_per_million: +editIn || 0, output_per_million: +editOut || 0, currency: editRow.currency || 'IRT' }),
      })
      setRows((prev) => prev.map((r) => (r.id === editRow.id ? { ...r, input_per_million: +editIn || 0, output_per_million: +editOut || 0 } : r)))
      toast('قیمت ذخیره شد', 'success')
      setEditRow(null)
    } catch {
      toast('خطا در ذخیره قیمت', 'error')
    } finally {
      setEditSaving(false)
    }
  }

  const openUpstream = (row: CatalogModelRow) => {
    setUpstreamRow(row); setUpstreamValue(row.upstream || '')
  }
  const saveUpstream = async () => {
    if (!upstreamRow || !upstreamValue) return
    setUpstreamSaving(true)
    try {
      const r = await api(`/api/admin/models/${encodeModelPath(upstreamRow.id)}/set-upstream`, {
        method: 'POST',
        body: JSON.stringify({ upstream: upstreamValue }),
      })
      const data = await r.json()
      setRows((prev) => prev.map((row) => (row.id === upstreamRow.id ? { ...row, upstream: data.upstream } : row)))
      toast('بالادست تغییر کرد', 'success')
      setUpstreamRow(null)
    } catch {
      toast('خطا در تغییر بالادست', 'error')
    } finally {
      setUpstreamSaving(false)
    }
  }

  // ─── Bulk actions ─────────────────────────────────────────────────────
  const runBulk = async (availability: 'available' | 'disabled') => {
    const ids = Array.from(selected)
    if (ids.length === 0) return
    setBulkBusy(true)
    try {
      await api('/api/admin/models/bulk-availability', {
        method: 'POST',
        body: JSON.stringify({ ids, availability }),
      })
      applyAvailability(ids, availability)
      toast(`${faNum(ids.length)} مدل ${availability === 'available' ? 'فعال' : 'غیرفعال'} شد`, 'success')
      clearSelection()
    } catch {
      toast('خطا در اجرای عملیات دسته‌ای', 'error')
    } finally {
      setBulkBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* ─── Filters ─── */}
      <div className="admin-card">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <div className="lg:col-span-2 flex items-center gap-2">
            <Icon name="search" size={14} className="text-muted" />
            <input
              className="input flex-1"
              placeholder="جستجو بر اساس شناسه یا نام..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select className="input" value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)}>
            <option value="">همه ارائه‌دهنده‌ها</option>
            {providers.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <select className="input" value={upstreamFilter} onChange={(e) => setUpstreamFilter(e.target.value)}>
            <option value="">همه بالادست‌ها</option>
            {upstreams.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
          <select className="input" value={availabilityFilter} onChange={(e) => setAvailabilityFilter(e.target.value)}>
            <option value="">همه وضعیت‌ها</option>
            {Object.entries(AVAILABILITY_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-muted">
            {faNum(filtered.length)} از {faNum(rows.length)} مدل
            {(search || providerFilter || upstreamFilter || availabilityFilter) && (
              <button className="btn btn-ghost btn-sm mr-2" onClick={resetFilters}>پاک‌کردن فیلترها</button>
            )}
          </p>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <Icon name="refresh" size={14} />
            <span>بازخوانی</span>
          </button>
        </div>
      </div>

      {/* ─── Bulk action bar ─── */}
      {selected.size > 0 && (
        <div className="admin-card" style={{ borderRight: '3px solid var(--accent)' }}>
          {bulkConfirm ? (
            <div className="flex items-center justify-between flex-wrap gap-2">
              <span className="text-sm text-primary">
                آیا از {bulkConfirm === 'available' ? 'فعال‌سازی' : 'غیرفعال‌سازی'} {faNum(selected.size)} مدل انتخابی مطمئن هستید؟
              </span>
              <div className="flex gap-2">
                <button className="btn btn-ghost btn-sm" onClick={() => setBulkConfirm(null)} disabled={bulkBusy}>انصراف</button>
                <button
                  className={`btn btn-sm ${bulkConfirm === 'disabled' ? 'btn-danger' : 'btn-primary'}`}
                  onClick={() => runBulk(bulkConfirm)}
                  disabled={bulkBusy}
                >
                  {bulkBusy ? '...' : 'بله، ادامه'}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between flex-wrap gap-2">
              <span className="text-sm text-primary">{faNum(selected.size)} مدل انتخاب شده</span>
              <div className="flex gap-2">
                <button className="btn btn-ghost btn-sm" onClick={clearSelection}>لغو انتخاب</button>
                <button className="btn btn-sm btn-secondary" onClick={() => setBulkConfirm('available')}>فعال‌سازی دسته‌ای</button>
                <button className="btn btn-sm btn-danger" onClick={() => setBulkConfirm('disabled')}>غیرفعال‌سازی دسته‌ای</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── Table ─── */}
      <div className="admin-card overflow-x-auto">
        {loading ? (
          <p className="text-center text-sm text-muted py-8">در حال بارگذاری...</p>
        ) : error ? (
          <p className="text-center text-sm text-danger py-8">{error}</p>
        ) : filtered.length === 0 ? (
          <p className="text-center text-sm text-muted py-8">موردی یافت نشد</p>
        ) : (
          <>
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="p-2"><input type="checkbox" checked={allPageSelected} onChange={toggleSelectAllPage} /></th>
                  <th className="text-right p-2">شناسه</th>
                  <th className="text-right p-2">نام نمایشی</th>
                  <th className="text-right p-2">ارائه‌دهنده</th>
                  <th className="text-right p-2">بالادست</th>
                  <th className="text-right p-2">وضعیت</th>
                  <th className="text-right p-2">خاستگاه</th>
                  <th className="text-right p-2">ورودی (تومان)</th>
                  <th className="text-right p-2">خروجی (تومان)</th>
                  <th className="text-right p-2">پنجره متن</th>
                  <th className="text-right p-2">آخرین تایید</th>
                  <th className="text-right p-2">عملیات</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((row) => {
                  const siblings = (byDisplayName.get(row.display_name) || []).filter((s) => s.id !== row.id)
                  const testResult = testResults[row.id]
                  const busy = busyId === row.id
                  return (
                    <tr key={row.id}>
                      <td className="p-2"><input type="checkbox" checked={selected.has(row.id)} onChange={() => toggleSelectOne(row.id)} /></td>
                      <td className="p-2 text-xs font-mono text-primary" title={row.id}>{row.id.length > 28 ? row.id.slice(0, 28) + '…' : row.id}</td>
                      <td className="p-2 text-xs">
                        {row.display_name}
                        {siblings.length > 0 && (
                          <span className="badge badge-accent mr-1" title={siblings.map((s) => `${s.provider} (${s.availability})`).join(', ')}>
                            +{faNum(siblings.length)} ارائه‌دهنده دیگر
                          </span>
                        )}
                      </td>
                      <td className="p-2 text-xs font-mono">{row.provider}</td>
                      <td className="p-2 text-xs font-mono">{row.upstream || '—'}</td>
                      <td className="p-2">
                        <button
                          className={`badge ${AVAILABILITY_BADGE[row.availability] || 'badge-accent'}`}
                          style={{ cursor: 'pointer' }}
                          disabled={busy}
                          onClick={() => toggleOne(row)}
                          title="کلیک برای تغییر وضعیت"
                        >
                          {busy ? '...' : AVAILABILITY_FA[row.availability] || row.availability}
                        </button>
                      </td>
                      <td className="p-2 text-xs text-muted">{row.provenance}</td>
                      <td className="p-2 text-xs">{faNum(row.input_per_million)}</td>
                      <td className="p-2 text-xs">{faNum(row.output_per_million)}</td>
                      <td className="p-2 text-xs">{faNum(row.context_window)}</td>
                      <td className="p-2 text-xs text-muted">{row.last_verified_at ? new Date(row.last_verified_at).toLocaleDateString('fa-IR') : '—'}</td>
                      <td className="p-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <button className="btn btn-sm btn-icon" title="تست" disabled={busy} onClick={() => testOne(row)}>
                            {busy ? <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" /> : <Icon name="refresh" size={14} />}
                          </button>
                          <button className="btn btn-sm btn-icon" title="ویرایش قیمت" onClick={() => openEdit(row)}>
                            <Icon name="pricing" size={14} />
                          </button>
                          <button className="btn btn-sm btn-icon" title="تغییر بالادست" onClick={() => openUpstream(row)}>
                            <Icon name="settings" size={14} />
                          </button>
                          {testResult && (
                            <span className="text-xs" style={{ color: testResult.ok ? 'var(--positive)' : 'var(--danger)' }}>
                              {testResult.ok ? `${faNum(testResult.latency_ms)}ms` : (testResult.error || 'خطا')}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>

            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
                <span className="text-xs text-muted">صفحه {faNum(pageSafe)} از {faNum(totalPages)}</span>
                <div className="flex gap-2">
                  <button className="btn btn-sm" disabled={pageSafe <= 1} onClick={() => setPage(Math.max(1, pageSafe - 1))}>قبلی</button>
                  <button className="btn btn-sm" disabled={pageSafe >= totalPages} onClick={() => setPage(pageSafe + 1)}>بعدی</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* ─── Edit price panel ─── */}
      {editRow && (
        <div className="admin-card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-sm text-primary">ویرایش قیمت — {editRow.display_name}</h3>
            <button className="btn btn-ghost btn-sm btn-icon" onClick={() => setEditRow(null)}><Icon name="close" size={14} /></button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium mb-1.5 text-secondary">ورودی / میلیون توکن (تومان)</label>
              <input className="input w-full" type="number" value={editIn} onChange={(e) => setEditIn(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5 text-secondary">خروجی / میلیون توکن (تومان)</label>
              <input className="input w-full" type="number" value={editOut} onChange={(e) => setEditOut(e.target.value)} />
            </div>
          </div>
          <button className="btn mt-4" onClick={saveEdit} disabled={editSaving}>
            {editSaving ? '...' : 'ذخیره قیمت'}
          </button>
        </div>
      )}

      {/* ─── Set upstream panel ─── */}
      {upstreamRow && (
        <div className="admin-card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-sm text-primary">تغییر بالادست — {upstreamRow.display_name}</h3>
            <button className="btn btn-ghost btn-sm btn-icon" onClick={() => setUpstreamRow(null)}><Icon name="close" size={14} /></button>
          </div>
          <p className="text-xs text-muted mb-3">
            شناسه: <span className="font-mono">{upstreamRow.id}</span> — ارائه‌دهنده: <span className="font-mono">{upstreamRow.provider}</span>
          </p>
          <div className="flex items-center gap-3">
            <select className="input flex-1" value={upstreamValue} onChange={(e) => setUpstreamValue(e.target.value)}>
              <option value="">انتخاب بالادست...</option>
              {upstreams.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
            <button className="btn" onClick={saveUpstream} disabled={upstreamSaving || !upstreamValue}>
              {upstreamSaving ? '...' : 'ذخیره'}
            </button>
          </div>
          {(byDisplayName.get(upstreamRow.display_name) || []).filter((s) => s.id !== upstreamRow.id).length > 0 && (
            <div className="mt-4 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
              <p className="text-xs text-muted mb-2">سایر ارائه‌دهنده‌های همین مدل منطقی:</p>
              <div className="space-y-1.5">
                {(byDisplayName.get(upstreamRow.display_name) || []).filter((s) => s.id !== upstreamRow.id).map((s) => (
                  <div key={s.id} className="flex items-center justify-between text-xs">
                    <span className="font-mono text-secondary">{s.provider} / {s.upstream || '—'}</span>
                    <span className={`badge ${AVAILABILITY_BADGE[s.availability] || 'badge-accent'}`}>{AVAILABILITY_FA[s.availability] || s.availability}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
