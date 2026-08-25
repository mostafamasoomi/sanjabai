'use client'

import { Fragment, useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice, Num } from '@/lib/format'
import { SectionHeader, StatCard } from './shared'
import { availabilityLabel, AVAILABILITY_FA } from './availability'

/* ═══════════════════════════════════════════════════════════════════════════
   Logical Models — Phase C, part 3. A "logical model" (`logical_model`) is
   what a user eventually sees ("GPT-4o"); each has N physical upstream
   candidates (`logical_model_candidate`, joined to `model_catalog`) it is
   allowed to route to. The clusterer seeded 449 logical models / 1154
   candidates and auto-approved only the 100 obvious singleton clusters —
   the other 1054 are `state='proposed'` and waiting on a human because 137
   underlying clusters tripped a price/context-window mismatch warning.
   This screen is that human review queue.

   Server contract (backend/admin_logical.py), registered bare (no /api
   prefix stripped by the Next.js proxy is handled by the `api` helper):
     GET  /api/admin/logical-models?q=&pending_only=&availability=&page=&limit=
        -> { items: [{ key, display_name, vendor, availability,
             routing_policy, pinned_candidate_id, candidate_counts:
             { total, proposed, approved, rejected } }], total, page, limit }
     GET  /api/admin/logical-models/{key}
        -> { ...logical_model fields, candidates: [{ id, catalog_id,
             priority, enabled, state, est_cost_usd_input/output, added_by,
             catalog: { id, provider, display_name, availability, currency,
             input_per_million, output_per_million, usd_input_per_million,
             usd_output_per_million } }] }
     POST /api/admin/logical-models/{key}/candidates/{id}  <- { state?,
          enabled?, priority? }
     POST /api/admin/logical-models/{key}/routing  <- { routing_policy?,
          pinned_candidate_id? }
     POST /api/admin/logical-models/{key}/availability  <- { availability }

   ── Why the queue, not a flat list ───────────────────────────────────────
   449 models / 1154 candidates cannot be worked through as one flat table.
   The default filter is "فقط دارای گزینهٔ بررسی‌نشده" (models with a
   `proposed` candidate) and the list is always sorted by proposed-count
   first — the admin's actual job is clearing that queue, not browsing.

   ── Guard rails mirrored client-side (server is authoritative) ──────────
   Pinning a candidate that is not approved+enabled, or publishing
   (availability=available) a model with zero eligible candidates, are both
   refused server-side with a Persian `detail`; this UI disables the
   corresponding buttons so the rejection is rare, not the safety net.

   All money is Toman via faPrice — never divided/multiplied by 10. The
   `est_cost_usd_*` / `catalog.usd_*_per_million` fields are USD estimates
   for admin comparison only, rendered via <Num unit="$">, never through
   faPrice (which would wrongly imply Toman).
   ═══════════════════════════════════════════════════════════════════════════ */

interface CandidateCounts { total: number; proposed: number; approved: number; rejected: number }

interface LogicalModelListItem {
  key: string
  display_name: string
  vendor: string | null
  availability: string
  routing_policy: string
  pinned_candidate_id: string | null
  candidate_counts: CandidateCounts
}

interface CandidateCatalog {
  id: string
  provider: string
  provider_model_id: string
  display_name: string
  availability: string
  currency: string
  input_per_million: number | null
  output_per_million: number | null
  usd_input_per_million: number | null
  usd_output_per_million: number | null
}

interface Candidate {
  id: number
  catalog_id: string
  priority: number
  enabled: boolean
  state: 'proposed' | 'approved' | 'rejected'
  est_cost_usd_input: number | null
  est_cost_usd_output: number | null
  added_by: string
  catalog: CandidateCatalog
}

interface LogicalModelDetail extends LogicalModelListItem {
  candidates: Candidate[]
}

interface LogicalModelsSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

const ROUTING_FA: Record<string, string> = {
  cheapest_healthy: 'ارزان‌ترین سالم', priority: 'بر اساس اولویت', pinned: 'پین‌شده',
}
const STATE_FA: Record<string, string> = { proposed: 'بررسی‌نشده', approved: 'تأییدشده', rejected: 'ردشده' }
const STATE_COLOR: Record<string, string> = { proposed: 'var(--warning, #f59e0b)', approved: '#22c55e', rejected: 'var(--danger, #ef4444)' }

function errMsg(e: unknown, fallback: string) {
  return e instanceof Error && e.message !== 'unauthorized' ? e.message : fallback
}

export default function LogicalModelsSection({ api }: LogicalModelsSectionProps) {
  const [rows, setRows] = useState<LogicalModelListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const limit = 25
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [pendingOnly, setPendingOnly] = useState(true)
  const [availFilter, setAvailFilter] = useState('')

  const [expanded, setExpanded] = useState<string | null>(null)
  const [detail, setDetail] = useState<LogicalModelDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async (p = page) => {
    setLoading(true)
    try {
      const qs = new URLSearchParams({
        page: String(p), limit: String(limit),
        pending_only: pendingOnly ? 'true' : 'false',
      })
      if (q.trim()) qs.set('q', q.trim())
      if (availFilter) qs.set('availability', availFilter)
      const res = await api(`/api/admin/logical-models?${qs.toString()}`)
      const body = await res.json()
      setRows(body.items || [])
      setTotal(body.total || 0)
      setPage(body.page || p)
    } catch (e) {
      toast(errMsg(e, 'خطا در دریافت فهرست مدل‌های منطقی'), 'error')
    } finally {
      setLoading(false)
    }
  }, [api, q, pendingOnly, availFilter, page])

  useEffect(() => { load(1) }, [q, pendingOnly, availFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadDetail = useCallback(async (key: string) => {
    setDetailLoading(true)
    try {
      const res = await api(`/api/admin/logical-models/${encodeURIComponent(key)}`)
      setDetail(await res.json())
    } catch (e) {
      toast(errMsg(e, 'خطا در دریافت جزئیات مدل'), 'error')
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }, [api])

  const toggleExpand = (key: string) => {
    if (expanded === key) { setExpanded(null); setDetail(null); return }
    setExpanded(key)
    setDetail(null)
    loadDetail(key)
  }

  // After any mutation on the expanded model: refresh its detail (source of
  // truth for the candidate table) and the list row (counts/availability
  // badges) without a full page reload.
  const refreshAfterMutation = async (key: string) => {
    await Promise.all([loadDetail(key), load(page)])
  }

  const runAction = async (busyKey: string, path: string, body: unknown, okMsg: string, key: string) => {
    setBusy(busyKey)
    try {
      await api(path, { method: 'POST', body: JSON.stringify(body) })
      toast(okMsg, 'success')
      await refreshAfterMutation(key)
    } catch (e) {
      toast(errMsg(e, 'ذخیره ناموفق بود'), 'error')
    } finally {
      setBusy(null)
    }
  }

  const setCandidateState = (key: string, id: number, state: string) =>
    runAction(`c${id}-state`, `/api/admin/logical-models/${key}/candidates/${id}`, { state },
      state === 'approved' ? 'گزینه تأیید شد' : 'گزینه رد شد', key)

  const toggleCandidateEnabled = (key: string, id: number, enabled: boolean) =>
    runAction(`c${id}-enabled`, `/api/admin/logical-models/${key}/candidates/${id}`, { enabled },
      enabled ? 'گزینه فعال شد' : 'گزینه غیرفعال شد', key)

  const savePriority = (key: string, id: number, priority: number) =>
    runAction(`c${id}-priority`, `/api/admin/logical-models/${key}/candidates/${id}`, { priority },
      'اولویت ذخیره شد', key)

  const pinCandidate = (key: string, catalogId: string) =>
    runAction(`pin-${catalogId}`, `/api/admin/logical-models/${key}/routing`,
      { pinned_candidate_id: catalogId, routing_policy: 'pinned' }, 'گزینه پین شد', key)

  const unpin = (key: string) =>
    runAction('unpin', `/api/admin/logical-models/${key}/routing`,
      { pinned_candidate_id: null, routing_policy: 'cheapest_healthy' }, 'پین برداشته شد', key)

  const setRoutingPolicy = (key: string, routing_policy: string) =>
    runAction('routing', `/api/admin/logical-models/${key}/routing`, { routing_policy },
      'سیاست مسیریابی ذخیره شد', key)

  const setAvailability = (key: string, availability: string) =>
    runAction('availability', `/api/admin/logical-models/${key}/availability`, { availability },
      'وضعیت در دسترس‌بودن ذخیره شد', key)

  const pendingModelsCount = rows.filter((r) => r.candidate_counts.proposed > 0).length
  const totalPages = Math.max(1, Math.ceil(total / limit))

  return (
    <div className="space-y-6">
      <SectionHeader
        title="مدل‌های منطقی"
        subtitle="بررسی و تأیید گزینه‌های فیزیکی هر مدل منطقی — صف کار: مدل‌هایی که گزینهٔ بررسی‌نشده دارند"
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard icon="models" label="کل مدل‌های منطقی" value={faNum(total)} color="var(--accent)" />
        <StatCard icon="warning" label="در این صفحه، دارای گزینهٔ بررسی‌نشده" value={faNum(pendingModelsCount)} color="var(--warning, #f59e0b)" />
        <StatCard icon="check" label="کل گزینه‌های تأییدشده (نمونه‌گیری صفحه)" value={faNum(rows.reduce((s, r) => s + r.candidate_counts.approved, 0))} color="#22c55e" />
      </div>

      <div className="admin-card">
        <div className="flex items-center gap-3 flex-wrap mb-4">
          <input className="input" placeholder="جستجوی کلید یا نام نمایشی…" value={q}
            onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
          <select className="input" value={availFilter} onChange={(e) => setAvailFilter(e.target.value)} style={{ maxWidth: 160 }}>
            <option value="">همهٔ وضعیت‌ها</option>
            {Object.entries(AVAILABILITY_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <label className="flex items-center gap-2 text-sm text-secondary cursor-pointer">
            <input type="checkbox" checked={pendingOnly} onChange={(e) => setPendingOnly(e.target.checked)} />
            فقط مدل‌های دارای گزینهٔ بررسی‌نشده (صف کار)
          </label>
        </div>

        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-3">مدل منطقی</th>
                <th className="text-right p-3">فروشنده</th>
                <th className="text-right p-3">وضعیت</th>
                <th className="text-right p-3">سیاست مسیریابی</th>
                <th className="text-right p-3">گزینه‌ها (بررسی‌نشده / تأیید / رد)</th>
                <th className="text-right p-3">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="p-6 text-center text-sm text-muted">در حال بارگذاری…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={6} className="p-6 text-center text-sm text-muted">موردی یافت نشد</td></tr>
              ) : (
                rows.map((r) => (
                  <Fragment key={r.key}>
                    <tr style={r.candidate_counts.proposed > 0 ? { background: 'color-mix(in srgb, var(--warning, #f59e0b) 8%, transparent)' } : undefined}>
                      <td className="p-3">
                        <div className="text-sm font-medium text-primary">{r.display_name}</div>
                        <div className="text-xs font-mono text-muted">{r.key}</div>
                      </td>
                      <td className="p-3 text-xs text-muted">{r.vendor || '—'}</td>
                      <td className="p-3"><span className="badge">{availabilityLabel(r.availability)}</span></td>
                      <td className="p-3 text-xs text-muted">{ROUTING_FA[r.routing_policy] || r.routing_policy}</td>
                      <td className="p-3 text-xs">
                        <span style={{ color: r.candidate_counts.proposed > 0 ? STATE_COLOR.proposed : 'var(--text-muted)' }}>{faNum(r.candidate_counts.proposed)}</span>
                        {' / '}<span style={{ color: STATE_COLOR.approved }}>{faNum(r.candidate_counts.approved)}</span>
                        {' / '}<span style={{ color: STATE_COLOR.rejected }}>{faNum(r.candidate_counts.rejected)}</span>
                      </td>
                      <td className="p-3">
                        <button className="btn btn-sm" onClick={() => toggleExpand(r.key)}>
                          {expanded === r.key ? 'بستن' : 'بررسی'}
                        </button>
                      </td>
                    </tr>
                    {expanded === r.key && (
                      <tr>
                        <td colSpan={6} className="p-3" style={{ background: 'var(--bg-elevated)' }}>
                          <CandidatesPanel
                            detail={detail} loading={detailLoading} busy={busy}
                            onApprove={(id) => setCandidateState(r.key, id, 'approved')}
                            onReject={(id) => setCandidateState(r.key, id, 'rejected')}
                            onReset={(id) => setCandidateState(r.key, id, 'proposed')}
                            onToggleEnabled={(id, en) => toggleCandidateEnabled(r.key, id, en)}
                            onSavePriority={(id, pr) => savePriority(r.key, id, pr)}
                            onPin={(catalogId) => pinCandidate(r.key, catalogId)}
                            onUnpin={() => unpin(r.key)}
                            onSetRoutingPolicy={(rp) => setRoutingPolicy(r.key, rp)}
                            onSetAvailability={(av) => setAvailability(r.key, av)}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between mt-4 text-xs text-muted">
          <span>{faNum(total)} مدل — صفحهٔ {faNum(page)} از {faNum(totalPages)}</span>
          <div className="flex gap-2">
            <button className="btn btn-sm" disabled={page <= 1 || loading} onClick={() => load(page - 1)}>قبلی</button>
            <button className="btn btn-sm" disabled={page >= totalPages || loading} onClick={() => load(page + 1)}>بعدی</button>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Candidate review panel (rendered inline under an expanded row) ────── */

function CandidatesPanel({
  detail, loading, busy,
  onApprove, onReject, onReset, onToggleEnabled, onSavePriority,
  onPin, onUnpin, onSetRoutingPolicy, onSetAvailability,
}: {
  detail: LogicalModelDetail | null
  loading: boolean
  busy: string | null
  onApprove: (id: number) => void
  onReject: (id: number) => void
  onReset: (id: number) => void
  onToggleEnabled: (id: number, enabled: boolean) => void
  onSavePriority: (id: number, priority: number) => void
  onPin: (catalogId: string) => void
  onUnpin: () => void
  onSetRoutingPolicy: (policy: string) => void
  onSetAvailability: (availability: string) => void
}) {
  const [priorityDrafts, setPriorityDrafts] = useState<Record<number, string>>({})

  if (loading || !detail) {
    return <p className="text-xs text-muted p-2">در حال بارگذاری جزئیات…</p>
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4 flex-wrap p-2 rounded" style={{ background: 'var(--bg-base)' }}>
        <div className="text-xs">
          <span className="text-muted">سیاست مسیریابی: </span>
          <select className="input" value={detail.routing_policy} disabled={busy === 'routing'}
            onChange={(e) => onSetRoutingPolicy(e.target.value)} style={{ maxWidth: 150, display: 'inline-block' }}>
            {Object.entries(ROUTING_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="text-xs">
          <span className="text-muted">وضعیت در دسترس‌بودن: </span>
          <select className="input" value={detail.availability} disabled={busy === 'availability'}
            onChange={(e) => onSetAvailability(e.target.value)} style={{ maxWidth: 130, display: 'inline-block' }}>
            {Object.entries(AVAILABILITY_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="text-xs text-muted">
          پین فعلی: {detail.pinned_candidate_id
            ? <><span className="font-mono">{detail.pinned_candidate_id}</span>{' '}
                <button className="text-xs underline" onClick={onUnpin} disabled={busy === 'unpin'}>برداشتن پین</button></>
            : 'ندارد'}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="admin-table w-full text-xs">
          <thead>
            <tr>
              <th className="text-right p-2">مدل فیزیکی</th>
              <th className="text-right p-2">وضعیت پروایدر</th>
              <th className="text-right p-2">قیمت (تومان / میلیون توکن)</th>
              <th className="text-right p-2">برآورد دلاری</th>
              <th className="text-right p-2">وضعیت گزینه</th>
              <th className="text-right p-2">فعال</th>
              <th className="text-right p-2">اولویت</th>
              <th className="text-right p-2">عملیات</th>
            </tr>
          </thead>
          <tbody>
            {detail.candidates.length === 0 ? (
              <tr><td colSpan={8} className="p-4 text-center text-muted">گزینه‌ای ثبت نشده است</td></tr>
            ) : detail.candidates.map((c) => {
              const eligible = c.state === 'approved' && c.enabled
              const isPinned = detail.pinned_candidate_id === c.catalog_id
              const draft = priorityDrafts[c.id] ?? String(c.priority)
              return (
                <tr key={c.id} style={isPinned ? { background: 'color-mix(in srgb, var(--accent) 10%, transparent)' } : undefined}>
                  <td className="p-2">
                    <div className="text-primary">{c.catalog.display_name}</div>
                    <div className="font-mono text-muted">{c.catalog_id}</div>
                    <div className="text-muted">{c.catalog.provider}</div>
                  </td>
                  <td className="p-2">{availabilityLabel(c.catalog.availability)}</td>
                  <td className="p-2">
                    <div>ورودی: {faPrice(c.catalog.input_per_million)}</div>
                    <div>خروجی: {faPrice(c.catalog.output_per_million)}</div>
                  </td>
                  <td className="p-2">
                    <div><Num value={c.catalog.usd_input_per_million} unit="$" decimals={3} /> / M in</div>
                    <div><Num value={c.catalog.usd_output_per_million} unit="$" decimals={3} /> / M out</div>
                  </td>
                  <td className="p-2">
                    <span style={{ color: STATE_COLOR[c.state] }}>{STATE_FA[c.state]}</span>
                  </td>
                  <td className="p-2">
                    <input type="checkbox" checked={c.enabled} disabled={busy === `c${c.id}-enabled`}
                      onChange={(e) => onToggleEnabled(c.id, e.target.checked)} />
                  </td>
                  <td className="p-2">
                    <input className="input" type="number" value={draft} style={{ maxWidth: 70 }}
                      onChange={(e) => setPriorityDrafts((p) => ({ ...p, [c.id]: e.target.value }))}
                      onBlur={() => {
                        const n = Number(draft)
                        if (Number.isInteger(n) && n !== c.priority) onSavePriority(c.id, n)
                      }} />
                  </td>
                  <td className="p-2">
                    <div className="flex items-center gap-1 flex-wrap">
                      {c.state !== 'approved' && (
                        <button className="btn btn-sm" disabled={busy === `c${c.id}-state`} onClick={() => onApprove(c.id)} title="تأیید">
                          <Icon name="check" size={12} />
                        </button>
                      )}
                      {c.state !== 'rejected' && (
                        <button className="btn btn-sm" disabled={busy === `c${c.id}-state`} onClick={() => onReject(c.id)} title="رد">
                          <Icon name="close" size={12} />
                        </button>
                      )}
                      {c.state !== 'proposed' && (
                        <button className="btn btn-sm" disabled={busy === `c${c.id}-state`} onClick={() => onReset(c.id)} title="بازگردانی به بررسی‌نشده">
                          <Icon name="refresh" size={12} />
                        </button>
                      )}
                      <button className="btn btn-sm" disabled={!eligible || isPinned || busy?.startsWith('pin-')}
                        onClick={() => onPin(c.catalog_id)}
                        title={eligible ? 'پین کردن این گزینه' : 'فقط گزینهٔ تأییدشده و فعال قابل پین است'}>
                        {isPinned ? 'پین‌شده' : 'پین'}
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
