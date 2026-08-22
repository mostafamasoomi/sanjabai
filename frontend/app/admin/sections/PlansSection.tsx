'use client'

import { Fragment, useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice, faDate } from '@/lib/format'
import { SectionHeader, Field } from './shared'

/* ═══════════════════════════════════════════════════════════════════════════
   Plans & Subscriptions — first frontend consumer of backend/admin.py's
   /admin/plans and /admin/subscriptions (grep across frontend/app/admin/
   found none before this file).

   Server contract (backend/admin.py):
     GET  /api/admin/plans            -> SELECT * FROM plans ORDER BY sort_order
     POST /api/admin/plans            <- { id, name_fa, name_en, price_monthly,
                                            monthly_token_quota, daily_token_limit,
                                            priority_queue, active, sort_order,
                                            models_allowed, features }
     GET  /api/admin/subscriptions?page=&limit= -> { subscriptions, total, page, limit }
                                            (read-only here -- no write endpoint
                                            for subscriptions exists in admin.py)

   ── Live schema drift found while building this (verified with a read-only
      `\\d plans` / `SELECT *` against the production DB, not guessed), FIXED
      in admin_create_plan since ──
   The `plans` table carries columns from overlapping migrations
   (0004_financial_core_part2 plus undocumented drift never captured by any
   migration file -- see admin.py::admin_create_plan's docstring) that were
   never reconciled at the schema level. admin_create_plan now papers over
   the drift so the two entry points into this table can't disagree:
     - `token_quota_monthly` (legacy, NOT NULL) and `monthly_token_quota`
       (the one this form edits) are now ALWAYS written together from the
       single quota value submitted here, on both create and update -- they
       can no longer diverge. Both are still surfaced below (`token_quota_monthly`
       shown next to it) so a value seeded before this fix landed is still
       visible if the two ever disagree from old data.
     - `name` (NOT NULL, no default), `price_yearly` (NOT NULL, no default)
       and `token_quota_monthly` (NOT NULL, no default) used to make every
       "create new plan" request 500 with an IntegrityError -- proven on a
       throwaway Postgres migrated via the real migrate.py chain, not
       guessed. All three are now set by the backend (`name` falls back to
       name_fa/name_en/the id; `price_yearly` defaults to
       `price_monthly * 12` since this form has no yearly-price field yet).
     - `features`/`models_allowed` binding into the jsonb columns (both
       INSERT and UPDATE) was proven broken (asyncpg `DataError` on a raw
       Python list) and is now fixed on the backend -- also proven on the
       same throwaway DB.

   `features` and `models_allowed` (both JSONB array columns) are still
   shown READ-ONLY, not editable, here -- that's a UI scope decision now,
   not a backend-safety one: the jsonb-bind bug that used to make editing
   them risky is fixed and verified, but no editable array control has been
   built for this form yet.
   ═══════════════════════════════════════════════════════════════════════════ */

interface PlanRow {
  id: string
  name: string | null
  description: string | null
  price_monthly: number
  price_yearly: number | null
  features: string[] | null
  token_quota_monthly: number | null
  active: boolean
  is_default: boolean
  created_at: string
  updated_at: string
  name_fa: string | null
  name_en: string | null
  monthly_token_quota: number | null
  daily_token_limit: number | null
  models_allowed: string[] | null
  priority_queue: boolean | null
  sort_order: number | null
}

interface SubscriptionRow {
  id: number
  user_id: number | null
  plan: string
  plan_id: string | null
  starts_at: string | null
  ends_at: string | null
  status: string
  monthly_token_quota: number
  tokens_used_this_period: number
  auto_renew: boolean
  cancelled_at: string | null
  price_paid: number
  created_at: string
  email: string | null
}

interface PlansSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

type PlanDraft = {
  name_fa: string; name_en: string; price_monthly: string
  monthly_token_quota: string; daily_token_limit: string
  priority_queue: boolean; active: boolean; sort_order: string
}

function toPlanDraft(p: PlanRow): PlanDraft {
  const s = (v: number | null) => (v == null ? '' : String(v))
  return {
    name_fa: p.name_fa ?? '', name_en: p.name_en ?? '', price_monthly: s(p.price_monthly),
    monthly_token_quota: s(p.monthly_token_quota), daily_token_limit: s(p.daily_token_limit),
    priority_queue: !!p.priority_queue, active: p.active, sort_order: s(p.sort_order ?? 0),
  }
}

const EMPTY_NEW_PLAN: PlanDraft & { id: string } = {
  id: '', name_fa: '', name_en: '', price_monthly: '', monthly_token_quota: '',
  daily_token_limit: '', priority_queue: false, active: true, sort_order: '0',
}

function NumInput({ value, onChange, width = 130, placeholder }: {
  value: string; onChange: (v: string) => void; width?: number; placeholder?: string
}) {
  return (
    <input className="input" type="number" min={0} value={value} placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)} style={{ maxWidth: width }} />
  )
}

const SUB_PAGE_SIZE = 50

export default function PlansSection({ api }: PlansSectionProps) {
  // ── Plans ──
  const [plansLoading, setPlansLoading] = useState(true)
  const [plansError, setPlansError] = useState(false)
  const [plans, setPlans] = useState<PlanRow[]>([])
  const [drafts, setDrafts] = useState<Record<string, PlanDraft>>({})
  const [savingId, setSavingId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const [showCreate, setShowCreate] = useState(false)
  const [newPlan, setNewPlan] = useState(EMPTY_NEW_PLAN)
  const [creating, setCreating] = useState(false)

  const loadPlans = useCallback(async () => {
    setPlansLoading(true); setPlansError(false)
    try {
      const res = await api('/api/admin/plans')
      const data: PlanRow[] = await res.json()
      setPlans(Array.isArray(data) ? data : [])
      const next: Record<string, PlanDraft> = {}
      for (const p of data) next[p.id] = toPlanDraft(p)
      setDrafts(next)
    } catch {
      setPlansError(true)
    } finally {
      setPlansLoading(false)
    }
  }, [api])

  useEffect(() => { loadPlans() }, [loadPlans])

  const setField = (id: string, field: keyof PlanDraft, value: string | boolean) => {
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], [field]: value } }))
  }
  const toggleExpanded = (id: string) => setExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  const savePlan = async (id: string) => {
    const d = drafts[id]
    if (!d) return
    if (!d.name_fa.trim() || !d.name_en.trim()) { toast('نام فارسی و انگلیسی الزامی است', 'error'); return }
    const n = (s: string) => (s.trim() === '' ? 0 : Number(s))
    setSavingId(id)
    try {
      await api('/api/admin/plans', {
        method: 'POST',
        body: JSON.stringify({
          id, name_fa: d.name_fa, name_en: d.name_en,
          price_monthly: n(d.price_monthly), monthly_token_quota: n(d.monthly_token_quota),
          daily_token_limit: n(d.daily_token_limit), priority_queue: d.priority_queue,
          active: d.active, sort_order: n(d.sort_order),
        }),
      })
      toast('پلن ذخیره شد', 'success')
      await loadPlans()
    } catch {
      toast('ذخیره پلن ناموفق بود', 'error')
    } finally {
      setSavingId(null)
    }
  }

  const createPlan = async () => {
    const id = newPlan.id.trim()
    if (!id) { toast('شناسهٔ پلن الزامی است', 'error'); return }
    if (!newPlan.name_fa.trim() || !newPlan.name_en.trim()) { toast('نام فارسی و انگلیسی الزامی است', 'error'); return }
    const n = (s: string) => (s.trim() === '' ? 0 : Number(s))
    setCreating(true)
    try {
      await api('/api/admin/plans', {
        method: 'POST',
        body: JSON.stringify({
          id, name_fa: newPlan.name_fa, name_en: newPlan.name_en,
          price_monthly: n(newPlan.price_monthly), monthly_token_quota: n(newPlan.monthly_token_quota),
          daily_token_limit: n(newPlan.daily_token_limit), priority_queue: newPlan.priority_queue,
          active: newPlan.active, sort_order: n(newPlan.sort_order),
        }),
      })
      toast('پلن جدید ایجاد شد', 'success')
      setNewPlan(EMPTY_NEW_PLAN)
      setShowCreate(false)
      await loadPlans()
    } catch {
      toast('ایجاد پلن ناموفق بود', 'error')
    } finally {
      setCreating(false)
    }
  }

  const freePlan = plans.find((p) => p.id === 'free')

  // ── Subscriptions ──
  const [subsLoading, setSubsLoading] = useState(true)
  const [subsError, setSubsError] = useState(false)
  const [subs, setSubs] = useState<SubscriptionRow[]>([])
  const [subsTotal, setSubsTotal] = useState(0)
  const [subsPage, setSubsPage] = useState(1)

  const loadSubs = useCallback(async (page: number) => {
    setSubsLoading(true); setSubsError(false)
    try {
      const res = await api(`/api/admin/subscriptions?page=${page}&limit=${SUB_PAGE_SIZE}`)
      const body = await res.json()
      setSubs(Array.isArray(body.subscriptions) ? body.subscriptions : [])
      setSubsTotal(typeof body.total === 'number' ? body.total : 0)
    } catch {
      setSubsError(true)
    } finally {
      setSubsLoading(false)
    }
  }, [api])

  useEffect(() => { loadSubs(subsPage) }, [loadSubs, subsPage])

  const subsTotalPages = Math.max(1, Math.ceil(subsTotal / SUB_PAGE_SIZE))

  return (
    <div className="space-y-6" dir="rtl">
      <SectionHeader title="پلن‌ها و اشتراک‌ها" subtitle={`${faNum(plans.length)} پلن — ${faNum(subsTotal)} اشتراک ثبت‌شده`} />

      {freePlan && (
        <div className="admin-card" style={{ borderRight: '3px solid var(--danger, #ef4444)' }}>
          <h3 className="font-semibold text-sm mb-2 flex items-center gap-1" style={{ color: 'var(--danger, #ef4444)' }}>
            <Icon name="warning" size={14} /> تناقض با قاعدهٔ محصول: «هیچ مدل رایگانی نداریم»
          </h3>
          <p className="text-xs text-secondary">
            پلن با شناسهٔ <b dir="ltr">free</b> در دیتابیس زنده وجود دارد: قیمت ماهانه = <b>{faPrice(freePlan.price_monthly)}</b>،
            سهمیهٔ توکن ماهانه (monthly_token_quota) = <b>{faNum(freePlan.monthly_token_quota)}</b> توکن
            {freePlan.token_quota_monthly != null && freePlan.token_quota_monthly !== freePlan.monthly_token_quota && (
              <> (ستون قدیمی token_quota_monthly = <b>{faNum(freePlan.token_quota_monthly)}</b>)</>
            )}
            ، is_default = <b>{freePlan.is_default ? 'بله' : 'خیر'}</b>.
          </p>
          <p className="text-xs mt-2 text-muted">
            طبق قاعدهٔ محصول هیچ مدلی رایگان نیست — حتی تأمین رایگان هم پولی فروخته می‌شود. این پلن حذف یا خودکار ویرایش نشد؛
            فقط اینجا برجسته شده تا مالک محصول تصمیم بگیرد (غیرفعال کردن، تغییر قیمت، یا حذفش).
          </p>
        </div>
      )}

      <div className="admin-card">
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-3">پلن</th>
                <th className="text-right p-3">فعال</th>
                <th className="text-right p-3">قیمت ماهانه</th>
                <th className="text-right p-3">سهمیهٔ توکن ماهانه</th>
                <th className="text-right p-3">سقف روزانه</th>
                <th className="text-right p-3">صف اولویت</th>
                <th className="text-right p-3">ترتیب نمایش</th>
                <th className="text-right p-3">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {plansLoading ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">در حال بارگذاری…</td></tr>
              ) : plansError ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
                  خطا در دریافت پلن‌ها — <button className="underline" onClick={loadPlans}>تلاش دوباره</button>
                </td></tr>
              ) : plans.length === 0 ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">پلنی یافت نشد</td></tr>
              ) : (
                plans.map((p) => {
                  const d = drafts[p.id]
                  if (!d) return null
                  const isFree = p.id === 'free'
                  return (
                    <Fragment key={p.id}>
                      <tr style={isFree ? { background: 'color-mix(in srgb, var(--danger, #ef4444) 8%, transparent)' } : undefined}>
                        <td className="p-3">
                          <input className="input mb-1" value={d.name_fa} placeholder="نام فارسی" onChange={(e) => setField(p.id, 'name_fa', e.target.value)} style={{ maxWidth: 160 }} />
                          <input className="input" value={d.name_en} placeholder="نام انگلیسی" onChange={(e) => setField(p.id, 'name_en', e.target.value)} style={{ maxWidth: 160 }} />
                          <div className="text-xs font-mono text-muted mt-1" dir="ltr">{p.id}{p.is_default ? ' · پیش‌فرض' : ''}</div>
                          <button className="text-xs text-muted underline mt-1" onClick={() => toggleExpanded(p.id)}>
                            {expanded.has(p.id) ? 'بستن جزئیات' : 'نمایش جزئیات'}
                          </button>
                        </td>
                        <td className="p-3"><input type="checkbox" checked={d.active} onChange={(e) => setField(p.id, 'active', e.target.checked)} /></td>
                        <td className="p-3">
                          <NumInput value={d.price_monthly} onChange={(v) => setField(p.id, 'price_monthly', v)} />
                          <div className="text-xs text-muted mt-1">{faPrice(Number(d.price_monthly) || 0)}</div>
                        </td>
                        <td className="p-3"><NumInput value={d.monthly_token_quota} onChange={(v) => setField(p.id, 'monthly_token_quota', v)} width={150} /></td>
                        <td className="p-3"><NumInput value={d.daily_token_limit} onChange={(v) => setField(p.id, 'daily_token_limit', v)} width={140} /></td>
                        <td className="p-3"><input type="checkbox" checked={d.priority_queue} onChange={(e) => setField(p.id, 'priority_queue', e.target.checked)} /></td>
                        <td className="p-3"><NumInput value={d.sort_order} onChange={(v) => setField(p.id, 'sort_order', v)} width={80} /></td>
                        <td className="p-3">
                          <button className="btn btn-sm" onClick={() => savePlan(p.id)} disabled={savingId === p.id} title="ذخیره">
                            {savingId === p.id ? <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" /> : <Icon name="check" size={14} />}
                          </button>
                        </td>
                      </tr>
                      {expanded.has(p.id) && (
                        <tr>
                          <td colSpan={8} className="p-3" style={{ background: 'var(--bg-elevated)' }}>
                            <div className="text-xs text-secondary space-y-1">
                              <p>توضیحات: {p.description || '—'}</p>
                              <p>قیمت سالانه (price_yearly): {p.price_yearly != null ? faPrice(p.price_yearly) : '—'}</p>
                              <p>ستون قدیمی token_quota_monthly: {faNum(p.token_quota_monthly)} — اکنون همیشه هم‌زمان با monthly_token_quota ذخیره می‌شود و نباید از آن واگرا شود.</p>
                              <p>امکانات (features، فقط نمایش): {p.features && p.features.length > 0 ? p.features.join('، ') : '—'}</p>
                              <p>مدل‌های مجاز (models_allowed، فقط نمایش): {p.models_allowed && p.models_allowed.length > 0 ? p.models_allowed.join('، ') : 'بدون محدودیت'}</p>
                              <p>ایجاد: {faDate(p.created_at)} — به‌روزرسانی: {faDate(p.updated_at)}</p>
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
            {showCreate ? 'بستن فرم پلن جدید' : '+ ایجاد پلن جدید'}
          </button>
          {showCreate && (
            <div className="mt-3 space-y-3">
              <p className="text-xs text-muted">
                ستون‌های الزامی <code dir="ltr">name</code>، <code dir="ltr">price_yearly</code> و
                <code dir="ltr" style={{ margin: '0 4px' }}>token_quota_monthly</code>
                توسط بک‌اند به‌صورت خودکار مقداردهی می‌شوند (قیمت سالانه پیش‌فرض = ۱۲ برابر قیمت ماهانه، مگر جای دیگری تعیین شود).
              </p>
              <div className="flex flex-wrap gap-3">
                <Field label="شناسه (id)"><input className="input" dir="ltr" value={newPlan.id} onChange={(e) => setNewPlan({ ...newPlan, id: e.target.value })} style={{ maxWidth: 140 }} /></Field>
                <Field label="نام فارسی"><input className="input" value={newPlan.name_fa} onChange={(e) => setNewPlan({ ...newPlan, name_fa: e.target.value })} style={{ maxWidth: 150 }} /></Field>
                <Field label="نام انگلیسی"><input className="input" value={newPlan.name_en} onChange={(e) => setNewPlan({ ...newPlan, name_en: e.target.value })} style={{ maxWidth: 150 }} /></Field>
                <Field label="قیمت ماهانه"><NumInput value={newPlan.price_monthly} onChange={(v) => setNewPlan({ ...newPlan, price_monthly: v })} /></Field>
                <Field label="سهمیهٔ توکن ماهانه"><NumInput value={newPlan.monthly_token_quota} onChange={(v) => setNewPlan({ ...newPlan, monthly_token_quota: v })} width={150} /></Field>
                <Field label="سقف روزانه"><NumInput value={newPlan.daily_token_limit} onChange={(v) => setNewPlan({ ...newPlan, daily_token_limit: v })} width={140} /></Field>
              </div>
              <button className="btn btn-sm" onClick={createPlan} disabled={creating}>{creating ? 'در حال ایجاد...' : 'ایجاد پلن'}</button>
            </div>
          )}
        </div>
      </div>

      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-3 text-primary">اشتراک‌های کاربران</h3>
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-3">کاربر</th>
                <th className="text-right p-3">پلن</th>
                <th className="text-right p-3">وضعیت</th>
                <th className="text-right p-3">سهمیهٔ توکن</th>
                <th className="text-right p-3">توکن مصرف‌شده</th>
                <th className="text-right p-3">مبلغ پرداختی</th>
                <th className="text-right p-3">تمدید خودکار</th>
                <th className="text-right p-3">تاریخ ایجاد</th>
              </tr>
            </thead>
            <tbody>
              {subsLoading ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">در حال بارگذاری…</td></tr>
              ) : subsError ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
                  خطا در دریافت اشتراک‌ها — <button className="underline" onClick={() => loadSubs(subsPage)}>تلاش دوباره</button>
                </td></tr>
              ) : subs.length === 0 ? (
                <tr><td colSpan={8} className="p-6 text-center text-sm text-muted">هیچ اشتراکی ثبت نشده (خروجی زندهٔ سرور: total = ۰)</td></tr>
              ) : (
                subs.map((s) => (
                  <tr key={s.id}>
                    <td className="p-3 text-xs" dir="ltr">{s.email || `#${s.user_id ?? '—'}`}</td>
                    <td className="p-3 text-xs" dir="ltr">{s.plan_id || s.plan}</td>
                    <td className="p-3 text-xs">{s.status}</td>
                    <td className="p-3 text-xs">{faNum(s.monthly_token_quota)}</td>
                    <td className="p-3 text-xs">{faNum(s.tokens_used_this_period)}</td>
                    <td className="p-3 text-xs">{faPrice(s.price_paid)}</td>
                    <td className="p-3 text-xs">{s.auto_renew ? 'بله' : 'خیر'}</td>
                    <td className="p-3 text-xs">{faDate(s.created_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {!subsLoading && !subsError && subsTotal > 0 && (
          <div className="flex items-center justify-between mt-3 text-xs text-muted">
            <span>صفحهٔ {faNum(subsPage)} از {faNum(subsTotalPages)} ({faNum(subsTotal)} اشتراک)</span>
            <div className="flex gap-2">
              <button className="btn btn-sm" onClick={() => setSubsPage((p) => Math.max(1, p - 1))} disabled={subsPage <= 1}>قبلی</button>
              <button className="btn btn-sm" onClick={() => setSubsPage((p) => Math.min(subsTotalPages, p + 1))} disabled={subsPage >= subsTotalPages}>بعدی</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
