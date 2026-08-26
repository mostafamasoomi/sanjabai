'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader, Field } from './shared'
import { freeTierStrings } from './FreeTierSection.strings'

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

export default function FreeTierSection({ api }: FreeTierSectionProps) {
  const lang = useLang()
  const s = freeTierStrings(lang)
  const f = fmt(lang)

  const FIELDS: { key: FieldKey; label: string; help: string; suffix: string }[] = [
    { key: 'free_hourly_limit', label: s.hourlyLabel, help: s.hourlyHelp, suffix: s.hourlySuffix },
    { key: 'free_lifetime_limit', label: s.lifetimeLabel, help: s.lifetimeHelp, suffix: s.lifetimeSuffix },
    { key: 'free_tier_max_input_per_million', label: s.maxInputLabel, help: s.maxInputHelp, suffix: s.maxInputSuffix },
  ]

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
        throw new Error(body.detail || s.serverError(String(res.status)))
      }
      const body: FreeTierData = await res.json()
      setData(body)
      setDraft({
        free_hourly_limit: String(body.values.free_hourly_limit),
        free_lifetime_limit: String(body.values.free_lifetime_limit),
        free_tier_max_input_per_million: String(body.values.free_tier_max_input_per_million),
      })
    } catch (e) {
      setError(e instanceof Error && e.message !== 'unauthorized' ? e.message : s.loadError)
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [api, s.loadError])

  useEffect(() => { load() }, [load])

  const changed: Partial<FreeTierValues> = {}
  if (data) {
    for (const field of FIELDS) {
      const raw = draft[field.key].trim()
      if (raw === '' || !/^\d+$/.test(raw)) continue
      const n = parseInt(raw, 10)
      if (n !== data.values[field.key]) changed[field.key] = n
    }
  }
  const dirty = Object.keys(changed).length > 0

  // A field the admin typed that is not a valid non-negative integer.
  const invalidField = data
    ? FIELDS.find(field => { const r = draft[field.key].trim(); return r !== '' && !/^\d+$/.test(r) })
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
        toast(body.detail || s.saveError, 'error')
        return
      }
      toast(s.saveSuccess, 'success')
      await load()
    } catch {
      toast(s.saveError, 'error')
    } finally {
      setSaving(false)
    }
  }

  if (error) {
    return (
      <div className="space-y-6">
        <SectionHeader title={s.title} subtitle={s.subtitle} />
        <div className="admin-card" style={{ borderRight: '3px solid var(--danger, #ef4444)' }}>
          <div className="flex items-center gap-2 mb-2">
            <Icon name="warning" size={18} style={{ color: 'var(--danger, #ef4444)' }} />
            <h3 className="font-semibold text-sm text-primary">{s.loadFailedTitle}</h3>
          </div>
          <p className="text-xs text-muted mb-4">{error}</p>
          <button className="btn btn-sm" onClick={load}>
            <Icon name="refresh" size={14} />
            <span>{s.retry}</span>
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title={s.title}
        subtitle={s.fullSubtitle}
      />

      {loading ? (
        <div className="admin-card p-6 text-center text-sm text-muted">{s.loading}</div>
      ) : !data ? (
        <div className="admin-card p-6 text-center text-sm text-muted">{s.noData}</div>
      ) : (
        <div className="admin-card space-y-4">
          {FIELDS.map(field => (
            <Field key={field.key} label={field.label}>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  className="input"
                  dir="ltr"
                  style={{ maxWidth: '12rem' }}
                  value={draft[field.key]}
                  disabled={saving}
                  onChange={(e) => setDraft(prev => ({ ...prev, [field.key]: e.target.value }))}
                />
                <span className="text-xs text-muted">{field.suffix}</span>
                {data.values[field.key] !== data.defaults[field.key] && (
                  <span className="text-xs text-muted">{s.defaultValue(f.num(data.defaults[field.key]))}</span>
                )}
              </div>
              <p className="text-xs text-muted mt-1">{field.help}</p>
            </Field>
          ))}

          {invalidField && (
            <p className="text-xs" style={{ color: 'var(--danger, #ef4444)' }}>
              {s.invalidField(invalidField.label)}
            </p>
          )}

          <div className="flex items-center gap-3 flex-wrap">
            <button className="btn btn-sm" onClick={save} disabled={!dirty || !!invalidField || saving}>
              {saving ? (
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
              ) : (
                <>
                  <Icon name="check" size={14} />
                  <span>{s.save}</span>
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
                {s.cancel}
              </button>
            )}
            {!dirty && !invalidField && <span className="text-xs text-muted">{s.noChanges}</span>}
          </div>

          {data.rows_missing.length > 0 && (
            <p className="text-xs text-muted">
              {s.rowsMissing(data.rows_missing.join(s.listSeparator))}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
