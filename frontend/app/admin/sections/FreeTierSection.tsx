'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { SectionHeader, Field } from './shared'

/* ═══════════════════════════════════════════════════════════════════════════
   محدودیت‌های حساب رایگان — سه عددی که رفتار کاربرِ بدون شارژ و بدون بسته را
   تعیین می‌کنند (services/free_tier.py، مهاجرت 0045):

     • سقف ساعتی        — چند پیام در هر ساعت
     • سقف مادام‌العمر   — چند پیام در کل عمر حساب (سقف سخت؛ بعدش باید شارژ کند)
     • سقف قیمت مدل      — کاربر رایگان فقط به مدل‌هایی با قیمت ورودی کمتر یا
                           مساوی این عدد (تومان بر میلیون توکن) دسترسی دارد

   حساب رایگان واقعاً رایگان است (هزینهٔ مدل را پلتفرم می‌دهد)، پس «فقط مدل
   ارزان» یک کنترل هزینه است، نه محدودیت الکی.

   Server contract (backend/admin_free_tier.py):
     GET  /api/admin/free-tier-settings -> { values, defaults, rows_missing }
     POST /api/admin/free-tier-settings <- { free_hourly_limit?, ... }  (اعداد صحیح)

   خطای GET مثل خطا نمایش داده می‌شود، نه مثل مقدار پیش‌فرض — همان قاعدهٔ
   WatchdogSection/SiteControlSection.
   ═══════════════════════════════════════════════════════════════════════════ */

interface FreeTierValues {
  free_hourly_limit: number
  free_lifetime_limit: number
  free_tier_max_input_per_million: number
}

interface FreeTierData {
  values: FreeTierValues
  defaults: FreeTierValues
  rows_missing: string[]
}

interface FreeTierSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

type FieldKey = keyof FreeTierValues

const FIELDS: { key: FieldKey; label: string; help: string; suffix: string }[] = [
  {
    key: 'free_hourly_limit',
    label: 'سقف پیام در ساعت',
    help: 'کاربر رایگان در هر ساعت حداکثر این تعداد پیام می‌تواند بفرستد. با پایان ساعت دوباره باز می‌شود.',
    suffix: 'پیام / ساعت',
  },
  {
    key: 'free_lifetime_limit',
    label: 'سقف پیام مادام‌العمر',
    help: 'کل پیام‌هایی که یک کاربر رایگان در تمام عمر حسابش می‌تواند بفرستد. پس از رسیدن به این عدد، تا شارژ حساب مسدود می‌ماند (سقف سخت، در پایگاه داده نگهداری می‌شود).',
    suffix: 'پیام (کل)',
  },
  {
    key: 'free_tier_max_input_per_million',
    label: 'سقف قیمت مدل‌های رایگان',
    help: 'کاربر رایگان فقط به مدل‌هایی دسترسی دارد که قیمت ورودی‌شان کمتر یا مساوی این عدد باشد (تومان بر میلیون توکن). مدل‌های گران‌تر برایش مسدودند تا هزینهٔ رایگان‌دهی کنترل شود.',
    suffix: 'تومان / میلیون توکن',
  },
]

export default function FreeTierSection({ api }: FreeTierSectionProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<FreeTierData | null>(null)
  const [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState<Record<FieldKey, string>>({
    free_hourly_limit: '',
    free_lifetime_limit: '',
    free_tier_max_input_per_million: '',
  })

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api('/api/admin/free-tier-settings')
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `خطای سرور (${res.status})`)
      }
      const body: FreeTierData = await res.json()
      setData(body)
      setDraft({
        free_hourly_limit: String(body.values.free_hourly_limit),
        free_lifetime_limit: String(body.values.free_lifetime_limit),
        free_tier_max_input_per_million: String(body.values.free_tier_max_input_per_million),
      })
    } catch (e) {
      setError(e instanceof Error && e.message !== 'unauthorized' ? e.message : 'خطا در دریافت تنظیمات حساب رایگان')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  const changed: Partial<FreeTierValues> = {}
  if (data) {
    for (const f of FIELDS) {
      const raw = draft[f.key].trim()
      if (raw === '' || !/^\d+$/.test(raw)) continue
      const n = parseInt(raw, 10)
      if (n !== data.values[f.key]) changed[f.key] = n
    }
  }
  const dirty = Object.keys(changed).length > 0

  // A field the admin typed that is not a valid non-negative integer.
  const invalidField = data
    ? FIELDS.find(f => { const r = draft[f.key].trim(); return r !== '' && !/^\d+$/.test(r) })
    : undefined

  const save = async () => {
    if (!data || !dirty || invalidField) return
    setSaving(true)
    try {
      const res = await api('/api/admin/free-tier-settings', {
        method: 'POST',
        body: JSON.stringify(changed),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        toast(body.detail || 'ذخیره ناموفق بود', 'error')
        return
      }
      toast('محدودیت‌های حساب رایگان ذخیره شد', 'success')
      await load()
    } catch {
      toast('ذخیره ناموفق بود', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (error) {
    return (
      <div className="space-y-6">
        <SectionHeader title="حساب رایگان" subtitle="سقف پیام و مدل‌های مجاز برای کاربر بدون شارژ" />
        <div className="admin-card" style={{ borderRight: '3px solid var(--danger, #ef4444)' }}>
          <div className="flex items-center gap-2 mb-2">
            <Icon name="warning" size={18} style={{ color: 'var(--danger, #ef4444)' }} />
            <h3 className="font-semibold text-sm text-primary">دریافت تنظیمات ناموفق بود</h3>
          </div>
          <p className="text-xs text-muted mb-4">{error}</p>
          <button className="btn btn-sm" onClick={load}>
            <Icon name="refresh" size={14} />
            <span>تلاش دوباره</span>
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="حساب رایگان"
        subtitle="سقف پیام ساعتی و مادام‌العمر و سقف قیمت مدل‌های مجاز برای کاربر بدون شارژ و بدون بسته — بدون نیاز به ری‌استارت"
      />

      {loading ? (
        <div className="admin-card p-6 text-center text-sm text-muted">در حال بارگذاری…</div>
      ) : !data ? (
        <div className="admin-card p-6 text-center text-sm text-muted">اطلاعاتی یافت نشد</div>
      ) : (
        <div className="admin-card space-y-4">
          {FIELDS.map(f => (
            <Field key={f.key} label={f.label}>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  className="input"
                  dir="ltr"
                  style={{ maxWidth: '12rem' }}
                  value={draft[f.key]}
                  disabled={saving}
                  onChange={(e) => setDraft(prev => ({ ...prev, [f.key]: e.target.value }))}
                />
                <span className="text-xs text-muted">{f.suffix}</span>
                {data.values[f.key] !== data.defaults[f.key] && (
                  <span className="text-xs text-muted">(پیش‌فرض: {data.defaults[f.key]})</span>
                )}
              </div>
              <p className="text-xs text-muted mt-1">{f.help}</p>
            </Field>
          ))}

          {invalidField && (
            <p className="text-xs" style={{ color: 'var(--danger, #ef4444)' }}>
              «{invalidField.label}» باید یک عدد صحیح نامنفی باشد.
            </p>
          )}

          <div className="flex items-center gap-3 flex-wrap">
            <button className="btn btn-sm" onClick={save} disabled={!dirty || !!invalidField || saving}>
              {saving ? (
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
              ) : (
                <>
                  <Icon name="check" size={14} />
                  <span>ذخیره</span>
                </>
              )}
            </button>
            {dirty && !saving && (
              <button
                className="btn btn-sm"
                style={{ background: 'var(--bg-elevated)' }}
                onClick={() => data && setDraft({
                  free_hourly_limit: String(data.values.free_hourly_limit),
                  free_lifetime_limit: String(data.values.free_lifetime_limit),
                  free_tier_max_input_per_million: String(data.values.free_tier_max_input_per_million),
                })}
              >
                انصراف
              </button>
            )}
            {!dirty && !invalidField && <span className="text-xs text-muted">تغییری برای ذخیره وجود ندارد</span>}
          </div>

          {data.rows_missing.length > 0 && (
            <p className="text-xs text-muted">
              ردیف‌های ذخیره‌سازی هنوز در پایگاه داده ساخته نشده‌اند ({data.rows_missing.join('، ')}) — مهاجرت
              0045 هنوز اعمال نشده است. مقادیر پیش‌فرض به‌کار می‌روند و اولین ذخیره ردیف را می‌سازد.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
