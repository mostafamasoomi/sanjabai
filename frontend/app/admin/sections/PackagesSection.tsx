'use client'

import { useState, useEffect, useCallback } from 'react'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader } from './shared'
import PackagesRow from './PackagesRow'
import PackagesCreateForm from './PackagesCreateForm'
import PackagesPremiumThreshold from './PackagesPremiumThreshold'
import {
  toDraft, isLossPath, EMPTY_NEW_PACKAGE,
  type Draft, type PackageRow, type PackagesSectionProps, type NewPackageDraft,
} from './PackagesTypes'
import { packagesSectionStrings } from './PackagesSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Packages — GapGPT-style credit packages: a Toman top-up that can also
   grant a request/token quota counted separately from Toman (migration
   0034: request_quota, token_quota, validity_days,
   max_cost_per_request_toman on credit_packages), plus two migration-0046
   rate-limit columns (rate_limit_per_window, premium_rate_limit_per_window)
   and an app_setting threshold that decides which models count as
   "expensive" for the second column.

   Split across sibling files, all under the 500-line cap:
     PackagesTypes.ts            -- shared types + pure helpers (no JSX)
     PackagesRow.tsx             -- one editable table row (+ legacy expander)
     PackagesCreateForm.tsx      -- the "+ افزودن بسته" form
     PackagesPremiumThreshold.tsx -- the "expensive model" price threshold field
     PackagesSection.tsx (here) -- data fetching/orchestration + the table shell

   Server contract (backend/admin_packages.py):
     GET  /api/admin/packages               -> full credit_packages rows
     POST /api/admin/packages/{id}          <- partial update of the
                                                editable fields below
     POST /api/admin/packages               <- create (id + fields)
     GET  /api/admin/premium-threshold      -> { value, default, row_missing }
     POST /api/admin/premium-threshold      <- { value: number }

   ── The charge / credit / quota / rate-limit split, FOUR different numbers ──
   `base_amount` is what the buyer PAYS. `total_credits` is what lands in
   their WALLET as Toman (already includes any bonus — it is NOT
   base_amount + bonus_credits, see below). `request_quota`/`token_quota`
   are a THIRD, separate thing: a count of requests/tokens that also creates
   a wallet-bypassing entitlement. `rate_limit_per_window` /
   `premium_rate_limit_per_window` are a FOURTH thing: pure per-5-hour-
   window message caps that never bypass the wallet — the second is a
   SUBSET counted from inside the first, never an additional cap.

   `price` / `credits` / `bonus_credits` / `name` are legacy columns that
   predate `base_amount`/`total_credits`/`bonus_percent` — grep across the
   backend found no purchase-flow code that still reads them (see the long
   comment at the top of admin_packages.py). They are kept editable here
   for parity with the API, but collapsed behind "فیلدهای قدیمی" per row
   and labeled as having no effect on checkout, so an edit here is never
   mistaken for changing what a buyer actually pays or receives.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function PackagesSection({ api }: PackagesSectionProps) {
  const lang = useLang()
  const s = packagesSectionStrings(lang)
  const f = fmt(lang)

  const [loading, setLoading] = useState(true)
  const [rows, setRows] = useState<PackageRow[]>([])
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  // Distinct from an empty table: a failed load must not look like "no
  // packages exist" once the toast fades.
  const [loadError, setLoadError] = useState<string | null>(null)

  const [showCreate, setShowCreate] = useState(false)
  const [newPackage, setNewPackage] = useState<NewPackageDraft>(EMPTY_NEW_PACKAGE)
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const res = await api('/api/admin/packages')
      const data: PackageRow[] = await res.json()
      setRows(data)
      const next: Record<string, Draft> = {}
      for (const p of data) next[p.id] = toDraft(p)
      setDrafts(next)
    } catch (err) {
      const msg = err instanceof Error && err.message !== 'unauthorized' ? err.message : s.loadError
      setLoadError(msg)
      toast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }, [api, s.loadError])

  useEffect(() => { load() }, [load])

  const setField = (id: string, field: keyof Draft, value: string | boolean) => {
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], [field]: value } }))
  }

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const save = async (id: string) => {
    const d = drafts[id]
    if (!d) return
    if (!d.name_fa.trim() || !d.name_en.trim()) {
      toast(s.nameRequired, 'error')
      return
    }
    if (isLossPath(d)) {
      toast(s.lossPathToastMessage, 'error')
      return
    }
    const n = (s: string) => (s.trim() === '' ? null : Number(s))
    const payload: Record<string, unknown> = {
      name_fa: d.name_fa, name_en: d.name_en, description: d.description === '' ? null : d.description,
      active: d.active,
      base_amount: n(d.base_amount), total_credits: n(d.total_credits), bonus_percent: n(d.bonus_percent),
      request_quota: n(d.request_quota), token_quota: n(d.token_quota), validity_days: n(d.validity_days),
      max_cost_per_request_toman: n(d.max_cost_per_request_toman),
      rate_limit_per_window: n(d.rate_limit_per_window),
      premium_rate_limit_per_window: n(d.premium_rate_limit_per_window),
      price: n(d.price) ?? 0, credits: n(d.credits) ?? 0, bonus_credits: n(d.bonus_credits) ?? 0,
    }
    setSaving(id)
    try {
      // api() throws before returning on a non-2xx response (see
      // ImagePricingSection.tsx's saveRowPrice), so a dedicated !res.ok
      // branch here is unreachable -- the catch below is the only path.
      await api(`/api/admin/packages/${encodeURIComponent(id)}`, {
        method: 'POST', body: JSON.stringify(payload),
      })
      toast(s.saved, 'success')
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.saveError, 'error')
    } finally {
      setSaving(null)
    }
  }

  const createPackage = async () => {
    const id = newPackage.id.trim()
    if (!id) { toast(s.idRequired, 'error'); return }
    if (!newPackage.name_fa.trim() || !newPackage.name_en.trim()) {
      toast(s.nameRequired, 'error')
      return
    }
    if (isLossPath(newPackage)) {
      toast(s.lossPathToastMessage, 'error')
      return
    }
    const n = (s: string) => (s.trim() === '' ? null : Number(s))
    setCreating(true)
    try {
      // backend/admin_packages.py::create_package -- `id` plus whichever of
      // the live/quota/rate-limit/text fields are given; the legacy
      // NOT-NULL trio (name/price/credits) is defaulted server-side.
      await api('/api/admin/packages', {
        method: 'POST',
        body: JSON.stringify({
          id, name_fa: newPackage.name_fa, name_en: newPackage.name_en,
          active: newPackage.active,
          base_amount: n(newPackage.base_amount), total_credits: n(newPackage.total_credits),
          bonus_percent: n(newPackage.bonus_percent),
          request_quota: n(newPackage.request_quota), token_quota: n(newPackage.token_quota),
          max_cost_per_request_toman: n(newPackage.max_cost_per_request_toman),
          rate_limit_per_window: n(newPackage.rate_limit_per_window),
          premium_rate_limit_per_window: n(newPackage.premium_rate_limit_per_window),
          validity_days: n(newPackage.validity_days),
        }),
      })
      toast(s.created, 'success')
      setNewPackage(EMPTY_NEW_PACKAGE)
      setShowCreate(false)
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.createError, 'error')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title={s.title}
        subtitle={s.subtitle(f.num(rows.length))}
      />

      <PackagesPremiumThreshold api={api} />

      <div className="admin-card" style={{ borderRight: '3px solid var(--accent)' }}>
        <h3 className="font-semibold text-sm mb-2 text-primary">{s.fourNumbersTitle}</h3>
        <ul className="text-xs text-muted space-y-1" style={{ listStyle: 'disc', paddingRight: 18 }}>
          <li><b className="text-secondary">{s.bulletPaid}</b> (base_amount){s.bulletPaidText}</li>
          <li><b className="text-secondary">{s.bulletCredited}</b> (total_credits){s.bulletCreditedText}</li>
          <li><b className="text-secondary">{s.bulletQuota}</b>{s.bulletQuotaText}</li>
          <li><b className="text-secondary">{s.bulletRateLimit}</b>{s.bulletRateLimitText}</li>
        </ul>
        <p className="text-xs mt-2" style={{ color: 'var(--warning, #f59e0b)' }}>
          {s.lossPathWarning}
        </p>
      </div>

      <div className="admin-card">
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-3">{s.colPackage}</th>
                <th className="text-right p-3">{s.colActive}</th>
                <th className="text-right p-3">{s.colBaseAmount}</th>
                <th className="text-right p-3">{s.colTotalCredits}</th>
                <th className="text-right p-3">{s.colBonusPercent}</th>
                <th className="text-right p-3">{s.colRequestQuota}</th>
                <th className="text-right p-3">{s.colTokenQuota}</th>
                <th className="text-right p-3">{s.colMaxCostPerRequest}</th>
                <th className="text-right p-3">
                  <div>{s.colRateLimit}</div>
                  <div className="text-xs text-muted font-normal">{s.colRateLimitSub}</div>
                </th>
                <th className="text-right p-3" title={s.colPremiumRateLimitTitle}>
                  <div>{s.colPremiumRateLimit}</div>
                  <div className="text-xs text-muted font-normal">{s.colRateLimitSub}</div>
                </th>
                <th className="text-right p-3">{s.colValidityDays}</th>
                <th className="text-right p-3">{s.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={11} className="p-6 text-center text-sm text-muted">{s.loading}</td></tr>
              ) : loadError ? (
                <tr><td colSpan={11} className="p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
                  {loadError} — <button className="underline" onClick={load}>{s.retry}</button>
                </td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={11} className="p-6 text-center text-sm text-muted">{s.noPackages}</td></tr>
              ) : (
                rows.map((p) => {
                  const d = drafts[p.id]
                  if (!d) return null
                  return (
                    <PackagesRow
                      key={p.id} p={p} d={d} saving={saving === p.id} expanded={expanded.has(p.id)}
                      onField={(field, value) => setField(p.id, field, value)}
                      onSave={() => save(p.id)}
                      onToggleExpanded={() => toggleExpanded(p.id)}
                    />
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <p className="text-xs text-muted mt-3">
          {s.premiumFootnote}
        </p>

        <div className="mt-4 pt-4 border-t" style={{ borderColor: 'var(--border)' }}>
          <button className="text-xs underline" onClick={() => setShowCreate((v) => !v)}>
            {showCreate ? s.closeCreateForm : s.openCreateForm}
          </button>
          {showCreate && (
            <PackagesCreateForm
              newPackage={newPackage} setNewPackage={setNewPackage}
              creating={creating} onCreate={createPackage}
            />
          )}
        </div>
      </div>
    </div>
  )
}
