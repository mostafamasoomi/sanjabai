'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice, faDate, faTime } from '@/lib/format'
import { SectionHeader, StatCard, Field, NumInput } from './shared'

/* ═══════════════════════════════════════════════════════════════════════════
   نرخ ارز — نمایش نرخ زندهٔ دلار به تومان، منبع تأمین آن، زمان آخرین
   به‌روزرسانی، مارک‌آپ ثابت قابل‌ویرایش، و فهرست منابعی که نرخ از آن‌ها
   واکشی می‌شود (Bonbast.com در کنار tgju، به‌علاوهٔ امکان افزودن مرجع دیگر
   توسط ادمین — درخواست مالک، ۳ شهریور ۱۴۰۵ / 2026-08-25).

   Self-contained (fetches via the `api` helper AdminPanel already exposes),
   same pattern as ./MarkupSection.tsx.

   Server contract (backend/exchange_rate_admin.py):
     GET  /api/admin/exchange-rate                    -> rate meta (unchanged shape)
     POST /api/admin/exchange-rate/refresh             -> same shape, forces a fresh resolve
     GET  /api/admin/exchange-rate/flat-markup         -> { flat_markup_toman, default_toman }
     POST /api/admin/exchange-rate/flat-markup         <- { flat_markup_toman }
     GET  /api/admin/exchange-rate/sources             -> { builtin: [...], configured: [...] }
     POST /api/admin/exchange-rate/sources             <- { source_key, display_name, url, unit,
                                                              extract_regex, priority, timeout_s }
     PATCH  /api/admin/exchange-rate/sources/{key}     <- any of { enabled, priority, timeout_s,
                                                              url, extract_regex, unit }
     DELETE /api/admin/exchange-rate/sources/{key}     -- only a non-builtin (admin-added) row

   `source` mirrors backend/content.py's resolver: 'db_override' > 'tgju' >
   an enabled row from `configured` (by priority; Bonbast is seeded as
   'bonbast') > 'er_api' > 'hardcoded_fallback', plus 'unknown' for a cache
   entry written before this feature existed (a stale/unhealthy state, not
   a normal tier -- rendered distinctly on purpose, see SOURCE_META below).
   All money here is raw Toman straight from the server -- never multiplied
   or divided.
   ═══════════════════════════════════════════════════════════════════════════ */

interface ExchangeRateMeta {
  rate_irt_bare: number
  flat_markup_irt: number
  rate_irt_effective: number
  markup_pct: number
  source: string
  fetched_at: string | null
  cache_ttl_remaining_s: number | null
}

interface BuiltinSourceInfo {
  source_key: string
  display_name: string
  kind: string
  editable: boolean
  note: string
}

interface ConfiguredSource {
  source_key: string
  display_name: string
  kind: string
  url: string | null
  unit: string
  extract_regex: string | null
  enabled: boolean
  priority: number
  timeout_s: number
  is_builtin: boolean
  editable: boolean
  deletable: boolean
  updated_at: string | null
}

interface ExchangeRateSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

const SOURCE_META: Record<string, { label: string; color: string; healthy: boolean }> = {
  db_override: { label: 'override دستی در پایگاه داده', color: 'var(--accent, #6366f1)', healthy: true },
  tgju: { label: 'بازار زنده — tgju.org', color: 'var(--success, #22c55e)', healthy: true },
  bonbast: { label: 'بازار زنده — Bonbast.com', color: 'var(--success, #22c55e)', healthy: true },
  er_api: { label: 'پشتیبان — open.er-api.com', color: 'var(--warning, #eab308)', healthy: true },
  hardcoded_fallback: { label: 'مقدار ثابت پشتیبان (کد)', color: 'var(--danger, #ef4444)', healthy: false },
  unknown: { label: 'نامشخص — کش قدیمی', color: 'var(--danger, #ef4444)', healthy: false },
}

function sourceMeta(source: string, configured: ConfiguredSource[]) {
  if (SOURCE_META[source]) return SOURCE_META[source]
  const row = configured.find((c) => c.source_key === source)
  if (row) return { label: `منبع سفارشی — ${row.display_name}`, color: 'var(--success, #22c55e)', healthy: true }
  return { label: source, color: 'var(--danger, #ef4444)', healthy: false }
}

const emptyNewSource = { source_key: '', display_name: '', url: '', unit: 'toman', extract_regex: '', priority: '100', timeout_s: '5' }

export default function ExchangeRateSection({ api }: ExchangeRateSectionProps) {
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [meta, setMeta] = useState<ExchangeRateMeta | null>(null)
  // Distinct from "no data yet": a failed load must not look like the
  // inert empty state once the toast fades.
  const [loadError, setLoadError] = useState<string | null>(null)

  const [flatMarkupDefault, setFlatMarkupDefault] = useState(2000)
  const [flatMarkupInput, setFlatMarkupInput] = useState('2000')
  const [savingFlatMarkup, setSavingFlatMarkup] = useState(false)

  const [builtin, setBuiltin] = useState<BuiltinSourceInfo[]>([])
  const [configured, setConfigured] = useState<ConfiguredSource[]>([])
  const [rowSaving, setRowSaving] = useState<string | null>(null)
  const [newSource, setNewSource] = useState(emptyNewSource)
  const [creatingSource, setCreatingSource] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [rateRes, flatRes, sourcesRes] = await Promise.all([
        api('/api/admin/exchange-rate'),
        api('/api/admin/exchange-rate/flat-markup'),
        api('/api/admin/exchange-rate/sources'),
      ])
      const rateBody: ExchangeRateMeta = await rateRes.json()
      const flatBody = await flatRes.json()
      const sourcesBody = await sourcesRes.json()
      setMeta(rateBody)
      setFlatMarkupDefault(Number(flatBody.default_toman) || 2000)
      setFlatMarkupInput(String(flatBody.flat_markup_toman ?? 2000))
      setBuiltin(sourcesBody.builtin || [])
      setConfigured(sourcesBody.configured || [])
    } catch (err) {
      const msg = err instanceof Error && err.message !== 'unauthorized' ? err.message : 'خطا در دریافت نرخ ارز'
      setLoadError(msg)
      toast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  const refresh = async () => {
    setRefreshing(true)
    try {
      const res = await api('/api/admin/exchange-rate/refresh', { method: 'POST' })
      const body: ExchangeRateMeta = await res.json()
      setMeta(body)
      toast('نرخ ارز به‌روزرسانی شد', 'success')
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'به‌روزرسانی نرخ ارز ناموفق بود', 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const saveFlatMarkup = async () => {
    const v = Number(flatMarkupInput)
    if (!Number.isFinite(v) || v < 0) {
      toast('مارک‌آپ نمی‌تواند منفی باشد', 'error')
      return
    }
    setSavingFlatMarkup(true)
    try {
      await api('/api/admin/exchange-rate/flat-markup', { method: 'POST', body: JSON.stringify({ flat_markup_toman: v }) })
      toast('مارک‌آپ ثابت ذخیره شد', 'success')
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'ذخیرهٔ مارک‌آپ ناموفق بود', 'error')
    } finally {
      setSavingFlatMarkup(false)
    }
  }

  const patchSource = async (key: string, body: Record<string, unknown>) => {
    setRowSaving(key)
    try {
      await api(`/api/admin/exchange-rate/sources/${encodeURIComponent(key)}`, { method: 'PATCH', body: JSON.stringify(body) })
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'به‌روزرسانی منبع ناموفق بود', 'error')
    } finally {
      setRowSaving(null)
    }
  }

  const deleteSource = async (key: string) => {
    if (!confirm(`منبع «${key}» حذف شود؟`)) return
    setRowSaving(key)
    try {
      await api(`/api/admin/exchange-rate/sources/${encodeURIComponent(key)}`, { method: 'DELETE' })
      toast('منبع حذف شد', 'success')
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'حذف منبع ناموفق بود', 'error')
    } finally {
      setRowSaving(null)
    }
  }

  const createSource = async () => {
    const priority = Number(newSource.priority)
    const timeout_s = Number(newSource.timeout_s)
    if (!newSource.source_key.trim() || !newSource.display_name.trim() || !newSource.url.trim() || !newSource.extract_regex.trim()) {
      toast('همهٔ فیلدها به‌جز اولویت و مهلت زمانی الزامی‌اند', 'error')
      return
    }
    if (!Number.isFinite(priority) || priority <= 0) {
      toast('اولویت باید عددی مثبت باشد', 'error')
      return
    }
    if (!Number.isFinite(timeout_s) || timeout_s <= 0 || timeout_s > 10) {
      toast('مهلت زمانی باید بین ۰ تا ۱۰ ثانیه باشد', 'error')
      return
    }
    setCreatingSource(true)
    try {
      await api('/api/admin/exchange-rate/sources', {
        method: 'POST',
        body: JSON.stringify({ ...newSource, priority, timeout_s }),
      })
      toast('منبع جدید افزوده شد', 'success')
      setNewSource(emptyNewSource)
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'افزودن منبع ناموفق بود', 'error')
    } finally {
      setCreatingSource(false)
    }
  }

  const sm = meta ? sourceMeta(meta.source, configured) : null

  return (
    <div className="space-y-6">
      <SectionHeader
        title="نرخ ارز"
        subtitle="نرخ زندهٔ دلار به تومان که قیمت همهٔ مدل‌ها بر اساس آن محاسبه می‌شود — نرخ بازار، مارک‌آپ ثابت قابل‌ویرایش، و منابع تأمین (tgju، Bonbast، و هر مرجع دیگری که اضافه کنید)"
      />

      {loading ? (
        <div className="admin-card p-6 text-center text-sm text-muted">در حال بارگذاری…</div>
      ) : loadError ? (
        <div className="admin-card p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
          {loadError}
          <div className="mt-2">
            <button className="btn btn-sm" onClick={load}>
              <Icon name="refresh" size={14} />
              تلاش دوباره
            </button>
          </div>
        </div>
      ) : !meta ? (
        <div className="admin-card p-6 text-center text-sm text-muted">اطلاعاتی یافت نشد</div>
      ) : (
        <>
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <StatCard icon="chart" label="نرخ بازار (بدون مارک‌آپ)" value={faPrice(Math.round(meta.rate_irt_bare))} color="var(--accent, #6366f1)" />
            <StatCard icon="plus" label="مارک‌آپ ثابت" value={faPrice(Math.round(meta.flat_markup_irt))} color="var(--warning, #eab308)" />
            <StatCard icon="wallet" label="نرخ مؤثر (سرو شده به کاربر)" value={faPrice(Math.round(meta.rate_irt_effective))} color="var(--success, #22c55e)" />
          </div>

          <div className="admin-card">
            <div className="flex items-center justify-between gap-4 flex-wrap mb-4">
              <h3 className="font-semibold text-sm text-primary">منبع و زمان به‌روزرسانی</h3>
              <button className="btn btn-sm" onClick={refresh} disabled={refreshing}>
                {refreshing ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (<><Icon name="refresh" size={14} /><span>واکشی فوری</span></>)}
              </button>
            </div>

            <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
              <div>
                <p className="text-xs text-muted mb-1">منبع نرخ</p>
                <span
                  className="badge"
                  title={sm && !sm.healthy ? 'وضعیت سالم نیست — این نرخ از یک کش قدیمی یا مقدار ثابت پشتیبان می‌آید، نه بازار زنده' : undefined}
                  style={{ color: sm?.color, borderColor: sm?.color }}
                >
                  {sm?.label}
                </span>
                {sm && !sm.healthy && (
                  <p className="text-xs mt-1" style={{ color: sm.color }}>
                    ⚠ این وضعیت سالم نیست — نرخ واقعی بازار تأمین نشده
                  </p>
                )}
              </div>
              <div>
                <p className="text-xs text-muted mb-1">آخرین واکشی</p>
                <p className="text-sm text-primary">
                  {meta.fetched_at ? `${faDate(meta.fetched_at)} — ${faTime(meta.fetched_at)}` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted mb-1">اعتبار کش</p>
                <p className="text-sm text-primary">
                  {meta.cache_ttl_remaining_s != null ? `${faNum(meta.cache_ttl_remaining_s)} ثانیهٔ دیگر` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted mb-1">درصد سود سراسری فعلی</p>
                <p className="text-sm text-primary">{faNum(meta.markup_pct)}٪</p>
              </div>
            </div>
          </div>

          <div className="admin-card">
            <p className="text-xs text-muted leading-6">
              نرخ سرو شده به کاربر همیشه برابر است با «نرخ بازار + مارک‌آپ ثابت»: {faPrice(Math.round(meta.rate_irt_bare))} + {faPrice(Math.round(meta.flat_markup_irt))} = {faPrice(Math.round(meta.rate_irt_effective))}.
              این عدد جدا از درصد سود هر مدل است که روی قیمت پایهٔ همان مدل اعمال می‌شود.
            </p>
          </div>

          {/* Flat markup edit */}
          <div className="admin-card">
            <h3 className="font-semibold text-sm text-primary mb-1">مارک‌آپ ثابت (تومان)</h3>
            <p className="text-xs text-muted mb-4">
              این عدد به نرخ خام بازار اضافه می‌شود تا نرخ مؤثر ساخته شود — مقدار پیش‌فرض {faPrice(flatMarkupDefault)}. صفر مجاز است (یعنی بدون مارک‌آپ ثابت)؛ عدد منفی رد می‌شود چون به فروش زیر نرخ بازار می‌انجامد.
            </p>
            <div className="flex items-end gap-3 flex-wrap">
              <Field label="مارک‌آپ ثابت (تومان)">
                <NumInput value={flatMarkupInput} onChange={setFlatMarkupInput} width={160} />
              </Field>
              <button className="btn btn-sm btn-primary" onClick={saveFlatMarkup} disabled={savingFlatMarkup}>
                {savingFlatMarkup ? '…' : (<><Icon name="check" size={14} /><span>ذخیره</span></>)}
              </button>
            </div>
          </div>

          {/* Sources */}
          <div className="admin-card">
            <h3 className="font-semibold text-sm text-primary mb-1">منابع نرخ ارز</h3>
            <p className="text-xs text-muted mb-4">
              ترتیب تلاش برای واکشی نرخ: override دستی، سپس tgju.org، سپس منابع فعال زیر بر اساس اولویت (عدد کوچک‌تر زودتر امتحان می‌شود)، سپس open.er-api.com، و در نهایت مقدار ثابت در کد.
            </p>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-right text-xs text-muted border-b border-line">
                    <th className="py-2 pl-2">منبع</th>
                    <th className="py-2 pl-2">نوع</th>
                    <th className="py-2 pl-2">اولویت</th>
                    <th className="py-2 pl-2">وضعیت</th>
                    <th className="py-2 pl-2">عملیات</th>
                  </tr>
                </thead>
                <tbody>
                  {builtin.map((b) => (
                    <tr key={b.source_key} className="border-b border-line/50">
                      <td className="py-2 pl-2">{b.display_name}</td>
                      <td className="py-2 pl-2 text-xs text-muted">کد ثابت</td>
                      <td className="py-2 pl-2 text-xs text-muted">—</td>
                      <td className="py-2 pl-2 text-xs text-muted" title={b.note}>غیرقابل‌ویرایش</td>
                      <td className="py-2 pl-2 text-xs text-muted">—</td>
                    </tr>
                  ))}
                  {configured.map((c) => (
                    <tr key={c.source_key} className="border-b border-line/50">
                      <td className="py-2 pl-2">
                        {c.display_name}
                        {c.is_builtin && <span className="text-xs text-muted"> (پایه)</span>}
                      </td>
                      <td className="py-2 pl-2 text-xs text-muted">{c.kind === 'bonbast' ? 'Bonbast' : `سفارشی (${c.unit === 'rial' ? 'ریال' : 'تومان'})`}</td>
                      <td className="py-2 pl-2">
                        <input
                          className="input" type="number" min={1} defaultValue={c.priority}
                          style={{ maxWidth: 80 }}
                          onBlur={(e) => {
                            const v = Number(e.target.value)
                            if (Number.isFinite(v) && v > 0 && v !== c.priority) patchSource(c.source_key, { priority: v })
                          }}
                        />
                      </td>
                      <td className="py-2 pl-2">
                        <button
                          className="badge" disabled={rowSaving === c.source_key}
                          style={{ color: c.enabled ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)', borderColor: c.enabled ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)' }}
                          onClick={() => patchSource(c.source_key, { enabled: !c.enabled })}
                        >
                          {c.enabled ? 'فعال' : 'غیرفعال'}
                        </button>
                      </td>
                      <td className="py-2 pl-2">
                        {c.deletable && (
                          <button className="btn btn-sm" disabled={rowSaving === c.source_key} onClick={() => deleteSource(c.source_key)} title="حذف">
                            <Icon name="trash" size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Add new source */}
            <div className="mt-6 pt-4 border-t border-line">
              <h4 className="font-semibold text-xs text-primary mb-3">افزودن منبع جدید</h4>
              <p className="text-xs text-muted mb-3">
                نشانی باید https باشد و به شبکهٔ داخلی سرور اشاره نکند. الگوی استخراج یک عبارت باقاعده با دقیقاً یک گروه () است که عدد نرخ را می‌گیرد — چیزی اجرا نمی‌شود، فقط یک عدد از متن صفحه استخراج می‌شود.
              </p>
              <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
                <Field label="کلید (انگلیسی، یکتا)">
                  <input className="input" value={newSource.source_key} onChange={(e) => setNewSource((s) => ({ ...s, source_key: e.target.value.trim().toLowerCase() }))} placeholder="example_site" />
                </Field>
                <Field label="نام نمایشی">
                  <input className="input" value={newSource.display_name} onChange={(e) => setNewSource((s) => ({ ...s, display_name: e.target.value }))} placeholder="Example Site" />
                </Field>
                <Field label="واحد">
                  <select className="input" value={newSource.unit} onChange={(e) => setNewSource((s) => ({ ...s, unit: e.target.value }))}>
                    <option value="toman">تومان</option>
                    <option value="rial">ریال</option>
                  </select>
                </Field>
                <Field label="اولویت">
                  <NumInput value={newSource.priority} onChange={(v) => setNewSource((s) => ({ ...s, priority: v }))} width={100} />
                </Field>
                <Field label="مهلت زمانی (ثانیه، حداکثر ۱۰)">
                  <NumInput value={newSource.timeout_s} onChange={(v) => setNewSource((s) => ({ ...s, timeout_s: v }))} width={100} />
                </Field>
              </div>
              <div className="grid gap-3 mt-3" style={{ gridTemplateColumns: '1fr' }}>
                <Field label="نشانی (https)">
                  <input className="input w-full" value={newSource.url} onChange={(e) => setNewSource((s) => ({ ...s, url: e.target.value }))} placeholder="https://example.com/usd-rate" />
                </Field>
                <Field label="الگوی استخراج (regex با یک گروه)">
                  <input className="input w-full" dir="ltr" value={newSource.extract_regex} onChange={(e) => setNewSource((s) => ({ ...s, extract_regex: e.target.value }))} placeholder={'USD\\s*=\\s*([\\d,]+)'} />
                </Field>
              </div>
              <button className="btn btn-sm btn-primary mt-3" onClick={createSource} disabled={creatingSource}>
                {creatingSource ? '…' : (<><Icon name="plus" size={14} /><span>افزودن منبع</span></>)}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
