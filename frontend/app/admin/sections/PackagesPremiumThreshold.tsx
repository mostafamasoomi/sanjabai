'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { Field } from './shared'
import type { PackagesSectionProps } from './PackagesTypes'

/* ═══════════════════════════════════════════════════════════════════════════
   The "expensive model" price threshold that decides which requests count
   against a package's `premium_rate_limit_per_window` (PackagesRow.tsx) --
   a model is "premium/expensive" when its input price is strictly greater
   than this many Toman per million tokens.

   Server contract (backend/admin_packages.py):
     GET  /api/admin/premium-threshold  -> { value, default, row_missing }
     POST /api/admin/premium-threshold  <- { value: number }

   Shape mirrors FreeTierSection.tsx (same load/dirty/save/cancel dance) but
   for a single value instead of three.
   ═══════════════════════════════════════════════════════════════════════════ */

interface ThresholdData {
  value: number
  default: number
  row_missing: boolean
}

export default function PackagesPremiumThreshold({ api }: PackagesSectionProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ThresholdData | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api('/api/admin/premium-threshold')
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `خطای سرور (${res.status})`)
      }
      const body: ThresholdData = await res.json()
      setData(body)
      setDraft(String(body.value))
    } catch (e) {
      setError(e instanceof Error && e.message !== 'unauthorized' ? e.message : 'خطا در دریافت آستانهٔ مدل گران')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  const trimmed = draft.trim()
  const invalid = trimmed !== '' && !/^\d+$/.test(trimmed)
  const dirty = !!data && !invalid && trimmed !== '' && Number(trimmed) !== data.value

  const save = async () => {
    if (!data || !dirty || invalid) return
    setSaving(true)
    try {
      const res = await api('/api/admin/premium-threshold', {
        method: 'POST',
        body: JSON.stringify({ value: Number(trimmed) }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        toast(body.detail || 'ذخیره ناموفق بود', 'error')
        return
      }
      toast('آستانهٔ مدل گران ذخیره شد', 'success')
      await load()
    } catch {
      toast('ذخیره ناموفق بود', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (error) {
    return (
      <div className="admin-card" style={{ borderRight: '3px solid var(--danger, #ef4444)' }}>
        <div className="flex items-center gap-2 mb-2">
          <Icon name="warning" size={18} style={{ color: 'var(--danger, #ef4444)' }} />
          <h3 className="font-semibold text-sm text-primary">دریافت آستانهٔ مدل گران ناموفق بود</h3>
        </div>
        <p className="text-xs text-muted mb-4">{error}</p>
        <button className="btn btn-sm" onClick={load}>
          <Icon name="refresh" size={14} />
          <span>تلاش دوباره</span>
        </button>
      </div>
    )
  }

  return (
    <div className="admin-card">
      {loading ? (
        <p className="text-sm text-muted">در حال بارگذاری…</p>
      ) : !data ? (
        <p className="text-sm text-muted">اطلاعاتی یافت نشد</p>
      ) : (
        <>
          <Field label="مدل گران یعنی قیمت ورودی بیشتر از">
            <div className="flex items-center gap-2">
              <input
                type="text" inputMode="numeric" className="input" dir="ltr"
                style={{ maxWidth: '12rem' }}
                value={draft} disabled={saving}
                onChange={(e) => setDraft(e.target.value)}
              />
              <span className="text-xs text-muted">تومان بر میلیون توکن</span>
              {data.value !== data.default && (
                <span className="text-xs text-muted">(پیش‌فرض: {data.default})</span>
              )}
            </div>
          </Field>
          <p className="text-xs text-muted mt-1">
            مدلی که قیمت ورودی‌اش بیشتر از این عدد باشد «گران» شمرده می‌شود و فقط سهمیهٔ ستون «از این، روی مدل گران» را مصرف می‌کند.
          </p>
          {invalid && (
            <p className="text-xs mt-1" style={{ color: 'var(--danger, #ef4444)' }}>
              مقدار باید یک عدد صحیح نامنفی باشد.
            </p>
          )}
          <div className="flex items-center gap-3 flex-wrap mt-3">
            <button className="btn btn-sm" onClick={save} disabled={!dirty || invalid || saving}>
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
              <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }}
                onClick={() => data && setDraft(String(data.value))}>
                انصراف
              </button>
            )}
            {!dirty && !invalid && <span className="text-xs text-muted">تغییری برای ذخیره وجود ندارد</span>}
          </div>
          {data.row_missing && (
            <p className="text-xs text-muted mt-2">
              این تنظیم هنوز در پایگاه داده ساخته نشده — مقدار پیش‌فرض به‌کار می‌رود و اولین ذخیره ردیف را می‌سازد.
            </p>
          )}
        </>
      )}
    </div>
  )
}
