'use client'

import { Fragment, useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice } from '@/lib/format'
import { SectionHeader, Field, NumInput } from './shared'

/* ═══════════════════════════════════════════════════════════════════════════
   Packages — GapGPT-style credit packages: a Toman top-up that can also
   grant a request/token quota counted separately from Toman (migration
   0034: request_quota, token_quota, validity_days,
   max_cost_per_request_toman on credit_packages).

   Self-contained (fetches its own data via the `api` prop), same pattern as
   ./MarkupSection.tsx, rather than threading state through AdminPanel.tsx.

   Server contract (backend/admin_packages.py):
     GET  /api/admin/packages               -> full credit_packages rows
     POST /api/admin/packages/{id}          <- partial update of the
                                                editable fields below
     POST /api/admin/packages               <- create (id + fields)

   ── The charge / credit / quota split, three different numbers ──────────
   `base_amount` is what the buyer PAYS. `total_credits` is what lands in
   their WALLET as Toman (already includes any bonus — it is NOT
   base_amount + bonus_credits, see below). `request_quota`/`token_quota`
   are a THIRD, separate thing: a count of requests/tokens, not Toman at
   all. An admin who conflates these will misconfigure a package, so the
   table below always shows all three side by side, never merges them.

   `price` / `credits` / `bonus_credits` / `name` are legacy columns that
   predate `base_amount`/`total_credits`/`bonus_percent` — grep across the
   backend found no purchase-flow code that still reads them (see the long
   comment at the top of admin_packages.py). They are kept editable here
   for parity with the API, but collapsed behind "فیلدهای قدیمی" per row
   and labeled as having no effect on checkout, so an edit here is never
   mistaken for changing what a buyer actually pays or receives.
   ═══════════════════════════════════════════════════════════════════════════ */

interface PackageRow {
  id: string
  name_fa: string | null
  name_en: string | null
  description: string | null
  active: boolean
  base_amount: number | null
  total_credits: number | null
  bonus_percent: number | null
  request_quota: number | null
  token_quota: number | null
  validity_days: number | null
  max_cost_per_request_toman: number | null
  price: number
  credits: number
  bonus_credits: number
  name: string
  sort_order: number
}

interface PackagesSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

type Draft = {
  name_fa: string
  name_en: string
  description: string
  active: boolean
  base_amount: string
  total_credits: string
  bonus_percent: string
  request_quota: string
  token_quota: string
  validity_days: string
  max_cost_per_request_toman: string
  price: string
  credits: string
  bonus_credits: string
}

function toDraft(p: PackageRow): Draft {
  const s = (v: number | null) => (v == null ? '' : String(v))
  return {
    name_fa: p.name_fa ?? '', name_en: p.name_en ?? '', description: p.description ?? '',
    active: p.active,
    base_amount: s(p.base_amount), total_credits: s(p.total_credits), bonus_percent: s(p.bonus_percent),
    request_quota: s(p.request_quota), token_quota: s(p.token_quota), validity_days: s(p.validity_days),
    max_cost_per_request_toman: s(p.max_cost_per_request_toman),
    price: s(p.price), credits: s(p.credits), bonus_credits: s(p.bonus_credits),
  }
}

/** true when a quota is set (draft) with no ceiling -- the loss path the
    backend rejects; mirrored here so the warning shows before a failed save.
    Takes only the three fields it needs so it also works for the create
    form's draft, which doesn't carry every `Draft` field. */
function isLossPath(d: { request_quota: string; token_quota: string; max_cost_per_request_toman: string }): boolean {
  const hasQuota = d.request_quota.trim() !== '' || d.token_quota.trim() !== ''
  return hasQuota && d.max_cost_per_request_toman.trim() === ''
}

type NewPackageDraft = {
  id: string; name_fa: string; name_en: string
  base_amount: string; total_credits: string; bonus_percent: string
  request_quota: string; token_quota: string; max_cost_per_request_toman: string
  validity_days: string; active: boolean
}

const EMPTY_NEW_PACKAGE: NewPackageDraft = {
  id: '', name_fa: '', name_en: '',
  base_amount: '', total_credits: '', bonus_percent: '',
  request_quota: '', token_quota: '', max_cost_per_request_toman: '',
  validity_days: '', active: true,
}

export default function PackagesSection({ api }: PackagesSectionProps) {
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
      const msg = err instanceof Error && err.message !== 'unauthorized' ? err.message : 'خطا در دریافت بسته‌ها'
      setLoadError(msg)
      toast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }, [api])

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
      toast('نام فارسی و انگلیسی الزامی است', 'error')
      return
    }
    if (isLossPath(d)) {
      toast(
        'بسته‌ای که سهمیهٔ درخواست یا توکن دارد باید سقف هزینهٔ هر درخواست هم داشته باشد، وگرنه مسیر ضررده است',
        'error',
      )
      return
    }
    const n = (s: string) => (s.trim() === '' ? null : Number(s))
    const payload: Record<string, unknown> = {
      name_fa: d.name_fa, name_en: d.name_en, description: d.description === '' ? null : d.description,
      active: d.active,
      base_amount: n(d.base_amount), total_credits: n(d.total_credits), bonus_percent: n(d.bonus_percent),
      request_quota: n(d.request_quota), token_quota: n(d.token_quota), validity_days: n(d.validity_days),
      max_cost_per_request_toman: n(d.max_cost_per_request_toman),
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
      toast('بسته ذخیره شد', 'success')
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'ذخیره ناموفق بود', 'error')
    } finally {
      setSaving(null)
    }
  }

  const createPackage = async () => {
    const id = newPackage.id.trim()
    if (!id) { toast('شناسهٔ بسته الزامی است', 'error'); return }
    if (!newPackage.name_fa.trim() || !newPackage.name_en.trim()) {
      toast('نام فارسی و انگلیسی الزامی است', 'error')
      return
    }
    if (isLossPath(newPackage)) {
      toast(
        'بسته‌ای که سهمیهٔ درخواست یا توکن دارد باید سقف هزینهٔ هر درخواست هم داشته باشد، وگرنه مسیر ضررده است',
        'error',
      )
      return
    }
    const n = (s: string) => (s.trim() === '' ? null : Number(s))
    setCreating(true)
    try {
      // backend/admin_packages.py::create_package -- `id` plus whichever of
      // the live/quota/text fields are given; the legacy NOT-NULL trio
      // (name/price/credits) is defaulted server-side, not sent from here.
      await api('/api/admin/packages', {
        method: 'POST',
        body: JSON.stringify({
          id, name_fa: newPackage.name_fa, name_en: newPackage.name_en,
          active: newPackage.active,
          base_amount: n(newPackage.base_amount), total_credits: n(newPackage.total_credits),
          bonus_percent: n(newPackage.bonus_percent),
          request_quota: n(newPackage.request_quota), token_quota: n(newPackage.token_quota),
          max_cost_per_request_toman: n(newPackage.max_cost_per_request_toman),
          validity_days: n(newPackage.validity_days),
        }),
      })
      toast('بستهٔ جدید ایجاد شد', 'success')
      setNewPackage(EMPTY_NEW_PACKAGE)
      setShowCreate(false)
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'ایجاد بسته ناموفق بود', 'error')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="بسته‌های اعتباری"
        subtitle={`${faNum(rows.length)} بسته — پرداختی، اعتبار واریزی و سهمیهٔ درخواست/توکن سه عدد جداگانه‌اند`}
      />

      <div className="admin-card" style={{ borderRight: '3px solid var(--accent)' }}>
        <h3 className="font-semibold text-sm mb-2 text-primary">سه عدد، سه معنای متفاوت</h3>
        <ul className="text-xs text-muted space-y-1" style={{ listStyle: 'disc', paddingRight: 18 }}>
          <li><b className="text-secondary">مبلغ پرداختی</b> (base_amount): مبلغی که کاربر واقعاً پرداخت می‌کند.</li>
          <li><b className="text-secondary">مبلغ واریزی به کیف پول</b> (total_credits): مبلغ نهایی (شامل پاداش) که به کیف پول کاربر اضافه می‌شود — این عدد از قبل شامل پاداش است، جمع‌کردن درصد پاداش رویش دوباره اشتباه است.</li>
          <li><b className="text-secondary">سهمیهٔ درخواست/توکن</b>: عددی کاملاً جدا از تومان — تعداد درخواست یا توکن، نه مبلغ.</li>
        </ul>
        <p className="text-xs mt-2" style={{ color: 'var(--warning, #f59e0b)' }}>
          🔴 بسته‌ای که سهمیهٔ درخواست یا توکن دارد باید «سقف هزینهٔ هر درخواست» هم داشته باشد — وگرنه کاربر می‌تواند کل سهمیه را روی گران‌ترین مدل خرج کند و هر درخواست ضررده شود. سرور این را رد می‌کند؛ این فرم فقط از قبل هشدار می‌دهد.
        </p>
      </div>

      <div className="admin-card">
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-3">بسته</th>
                <th className="text-right p-3">فعال</th>
                <th className="text-right p-3">مبلغ پرداختی</th>
                <th className="text-right p-3">مبلغ واریزی به کیف پول</th>
                <th className="text-right p-3">درصد پاداش</th>
                <th className="text-right p-3">سهمیهٔ درخواست</th>
                <th className="text-right p-3">سهمیهٔ توکن</th>
                <th className="text-right p-3">سقف هزینهٔ هر درخواست</th>
                <th className="text-right p-3">مدت اعتبار (روز)</th>
                <th className="text-right p-3">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={10} className="p-6 text-center text-sm text-muted">در حال بارگذاری…</td></tr>
              ) : loadError ? (
                <tr><td colSpan={10} className="p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
                  {loadError} — <button className="underline" onClick={load}>تلاش دوباره</button>
                </td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={10} className="p-6 text-center text-sm text-muted">بسته‌ای یافت نشد</td></tr>
              ) : (
                rows.map((p) => {
                  const d = drafts[p.id]
                  if (!d) return null
                  const warn = isLossPath(d)
                  return (
                    <Fragment key={p.id}>
                      <tr style={warn ? { background: 'color-mix(in srgb, var(--warning, #f59e0b) 10%, transparent)' } : undefined}>
                        <td className="p-3">
                          <input className="input mb-1" value={d.name_fa} placeholder="نام فارسی"
                            onChange={(e) => setField(p.id, 'name_fa', e.target.value)} style={{ maxWidth: 160 }} />
                          <input className="input" value={d.name_en} placeholder="نام انگلیسی"
                            onChange={(e) => setField(p.id, 'name_en', e.target.value)} style={{ maxWidth: 160 }} />
                          <div className="text-xs font-mono text-muted mt-1">{p.id}</div>
                          <button className="text-xs text-muted underline mt-1" onClick={() => toggleExpanded(p.id)}>
                            {expanded.has(p.id) ? 'بستن فیلدهای قدیمی' : 'نمایش فیلدهای قدیمی'}
                          </button>
                        </td>
                        <td className="p-3">
                          <input type="checkbox" checked={d.active} onChange={(e) => setField(p.id, 'active', e.target.checked)} />
                        </td>
                        <td className="p-3">
                          <NumInput value={d.base_amount} onChange={(v) => setField(p.id, 'base_amount', v)} />
                          <div className="text-xs text-muted mt-1">{faPrice(p.base_amount)}</div>
                        </td>
                        <td className="p-3">
                          <NumInput value={d.total_credits} onChange={(v) => setField(p.id, 'total_credits', v)} />
                          <div className="text-xs text-muted mt-1">{faPrice(p.total_credits)}</div>
                        </td>
                        <td className="p-3"><NumInput value={d.bonus_percent} onChange={(v) => setField(p.id, 'bonus_percent', v)} width={80} /></td>
                        <td className="p-3"><NumInput value={d.request_quota} onChange={(v) => setField(p.id, 'request_quota', v)} placeholder="بدون سهمیه" /></td>
                        <td className="p-3"><NumInput value={d.token_quota} onChange={(v) => setField(p.id, 'token_quota', v)} placeholder="بدون سهمیه" /></td>
                        <td className="p-3">
                          <NumInput value={d.max_cost_per_request_toman} onChange={(v) => setField(p.id, 'max_cost_per_request_toman', v)} placeholder="بدون سقف" />
                          {warn && (
                            <div className="text-xs flex items-center gap-1 mt-1" style={{ color: 'var(--warning, #f59e0b)' }}>
                              <Icon name="warning" size={12} />
                              <span>سقف لازم است</span>
                            </div>
                          )}
                        </td>
                        <td className="p-3"><NumInput value={d.validity_days} onChange={(v) => setField(p.id, 'validity_days', v)} width={90} placeholder="بدون انقضا" /></td>
                        <td className="p-3">
                          <button className="btn btn-sm" onClick={() => save(p.id)} disabled={saving === p.id} title="ذخیره">
                            {saving === p.id ? (
                              <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                            ) : <Icon name="check" size={14} />}
                          </button>
                        </td>
                      </tr>
                      {expanded.has(p.id) && (
                        <tr>
                          <td colSpan={10} className="p-3" style={{ background: 'var(--bg-elevated)' }}>
                            <p className="text-xs text-muted mb-2">
                              فیلدهای قدیمی — این‌ها روی مبلغ پرداختی یا واریزی واقعی هیچ اثری ندارند (کد خرید فقط
                              مبلغ پرداختی و مبلغ واریزی بالا را می‌خواند)، صرفاً برای سازگاری با داده‌های قدیمی نگه داشته شده‌اند.
                            </p>
                            <div className="flex flex-wrap gap-4">
                              <Field label="توضیحات">
                                <input className="input" value={d.description}
                                  onChange={(e) => setField(p.id, 'description', e.target.value)} style={{ minWidth: 220 }} />
                              </Field>
                              <Field label="price (قدیمی)">
                                <NumInput value={d.price} onChange={(v) => setField(p.id, 'price', v)} width={110} />
                              </Field>
                              <Field label="credits (قدیمی)">
                                <NumInput value={d.credits} onChange={(v) => setField(p.id, 'credits', v)} width={110} />
                              </Field>
                              <Field label="bonus_credits (قدیمی)">
                                <NumInput value={d.bonus_credits} onChange={(v) => setField(p.id, 'bonus_credits', v)} width={110} />
                              </Field>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-4 pt-4 border-t" style={{ borderColor: 'var(--border)' }}>
          <button className="text-xs underline" onClick={() => setShowCreate((v) => !v)}>
            {showCreate ? 'بستن فرم بستهٔ جدید' : '+ افزودن بسته'}
          </button>
          {showCreate && (
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap gap-3 items-end">
                <Field label="شناسه (id)">
                  <input className="input" dir="ltr" value={newPackage.id}
                    onChange={(e) => setNewPackage({ ...newPackage, id: e.target.value })} style={{ maxWidth: 140 }} />
                </Field>
                <Field label="نام فارسی">
                  <input className="input" value={newPackage.name_fa}
                    onChange={(e) => setNewPackage({ ...newPackage, name_fa: e.target.value })} style={{ maxWidth: 150 }} />
                </Field>
                <Field label="نام انگلیسی">
                  <input className="input" value={newPackage.name_en}
                    onChange={(e) => setNewPackage({ ...newPackage, name_en: e.target.value })} style={{ maxWidth: 150 }} />
                </Field>
                <Field label="فعال">
                  <input type="checkbox" checked={newPackage.active}
                    onChange={(e) => setNewPackage({ ...newPackage, active: e.target.checked })} />
                </Field>
              </div>
              <div className="flex flex-wrap gap-3 items-end">
                <Field label="مبلغ پرداختی">
                  <NumInput value={newPackage.base_amount} onChange={(v) => setNewPackage({ ...newPackage, base_amount: v })} />
                </Field>
                <Field label="مبلغ واریزی به کیف پول">
                  <NumInput value={newPackage.total_credits} onChange={(v) => setNewPackage({ ...newPackage, total_credits: v })} />
                </Field>
                <Field label="درصد پاداش">
                  <NumInput value={newPackage.bonus_percent} onChange={(v) => setNewPackage({ ...newPackage, bonus_percent: v })} width={80} />
                </Field>
                <Field label="سهمیهٔ درخواست">
                  <NumInput value={newPackage.request_quota} onChange={(v) => setNewPackage({ ...newPackage, request_quota: v })} placeholder="بدون سهمیه" />
                </Field>
                <Field label="سهمیهٔ توکن">
                  <NumInput value={newPackage.token_quota} onChange={(v) => setNewPackage({ ...newPackage, token_quota: v })} placeholder="بدون سهمیه" />
                </Field>
                <Field label="سقف هزینهٔ هر درخواست">
                  <NumInput
                    value={newPackage.max_cost_per_request_toman}
                    onChange={(v) => setNewPackage({ ...newPackage, max_cost_per_request_toman: v })}
                    placeholder="بدون سقف"
                  />
                </Field>
                <Field label="مدت اعتبار (روز)">
                  <NumInput value={newPackage.validity_days} onChange={(v) => setNewPackage({ ...newPackage, validity_days: v })} width={90} placeholder="بدون انقضا" />
                </Field>
              </div>
              {isLossPath(newPackage) && (
                <div className="text-xs flex items-center gap-1" style={{ color: 'var(--warning, #f59e0b)' }}>
                  <Icon name="warning" size={12} />
                  <span>سهمیه بدون سقف هزینه — سرور این را رد می‌کند</span>
                </div>
              )}
              <button className="btn btn-sm" onClick={createPackage} disabled={creating}>
                {creating ? 'در حال ایجاد...' : 'ایجاد بسته'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
